from typing import TypedDict,Literal, Any
from langchain_core.messages import HumanMessage,SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel , Field
from dotenv import load_dotenv
import os 
import requests
from langgraph.types import interrupt
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph , START , END 
import asyncio
import json
from swiggy_auth import create_oauth_provider
import re
load_dotenv()

api_key = os.getenv("USDA_API_KEY")

class AgentState(TypedDict):
    user_query : str
    budget_amount: float | None
    food_type : str|None
    protein_target: float | None
    protein_consumed: float | None
    protein_deficit: float | None
    budget_food_type_filtered : str | None
    foods_with_nutrition: list[dict[str, Any]]
    recommendation : str
    approval:bool
    search_results: list[dict]
    ranked_items: list[dict]
    follow_up_question: str | None
    rewrited_user_query : str|None
    selected_food : str|None
    restaurant_id : str| None
    address_id: str|None
    selected_menu : dict|None
    menu_item_id : str|None
    cart_response : Any|None
    cart : Any|None
    confirmation_response: str | None = None
    confirm : bool|None = None
    placed_order: str | None = None
    user_selection: str | None = None
llm = ChatOllama(model = "qwen2.5:3b")


class extract(BaseModel):
    amount : float|None  = Field(description ="extract the amount from the user input default value is none")
    protein_target : float|None = Field(description = "extract the target protein from the user input default value is none")
    protein_consumed : float|None = Field(description = "extract the consumed protein from the user query default value is none")
    food_type: str | None = Field(
    description="Extract the food type (vegetarian or non_vegetarian). Default is None."
)
system_prompt = """You are a constraint extraction AI.

The input may be:
1. A complete user request.
2. The previous query followed by the user's answer to a follow-up question.

Extract these fields:

- amount → budget
- protein_target → desired protein intake (grams)
- protein_consumed → protein already consumed (grams)
- food_type → "vegetarian" or "non_vegetarian"

Rules:

- Extract only explicitly mentioned information.
- Never guess or calculate values.
- Never assign one number to multiple fields.
- If a field was already extracted previously and the latest message doesn't change it, keep the previous value.
- Do NOT overwrite existing values with None.

Follow-up handling:

If the latest reply is only a number:
- If the previous question asked for budget → amount
- If it asked for desired protein → protein_target
- If it asked for consumed protein → protein_consumed

If the latest reply is:
veg, vegetarian → vegetarian

non veg, non-veg, chicken, egg, fish, meat → non_vegetarian

Return food_type exactly as:
- vegetarian
- non_vegetarian

Examples:

User: "I have ₹300"
amount=300

User: "Need 120g protein"
protein_target=120

User: "Already consumed 40g protein"
protein_consumed=40

User: "Veg food under ₹200"
amount=200
food_type=vegetarian

User: "Non veg food under ₹300"
amount=300
food_type=non_vegetarian

User: "Need 30g protein, budget ₹250, non veg"
amount=250
protein_target=30
food_type=non_vegetarian

Previous Query:
I want non veg food under ₹200

User:
40

amount=200
protein_target=40
food_type=non_vegetarian

Return None only for fields that are genuinely unavailable.
"""""
llm_with_structure = llm.with_structured_output(extract)

def constraint_extract(state: AgentState):
    query = state["user_query"]

    response: extract = llm_with_structure.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]
    )

    return {
        "budget_amount": (
            response.amount
            if response.amount is not None
            else state.get("budget_amount")
        ),
        "protein_target": (
            response.protein_target
            if response.protein_target is not None
            else state.get("protein_target")
        ),
        "protein_consumed": (
            response.protein_consumed
            if response.protein_consumed is not None
            else state.get("protein_consumed")
        ),
        "food_type": (
        response.food_type
        if response.food_type is not None
        else state.get("food_type")
        )
    }

def Missing_constraint(state: AgentState):

    missing = []

    if state["budget_amount"] is None:
        missing.append("budget")

    if state["protein_target"] is None:
        missing.append("protein_target")

    if state["food_type"] is None:
        missing.append("food_type")

    if not missing:
        return {}

    if len(missing) == 1:

        if missing[0] == "budget":
            question = "💰 What is your budget?"

        elif missing[0] == "protein_target":
            question = "💪 What is your desired protein intake (in grams)?"

        elif missing[0] == "food_type":
            question = "🥗 Do you prefer vegetarian or non-vegetarian food?"

    else:

        question = "Please provide the following:\n"

        if "budget" in missing:
            question += "\n• Budget"

        if "protein_target" in missing:
            question += "\n• Protein target (grams)"

        if "food_type" in missing:
            question += "\n• Food preference (Veg / Non-Veg)"

    # Pause graph
    answer = interrupt(question)

    return {
        "user_query": state["user_query"] + "\n" + answer
    }

def constraint_router(state: AgentState):

    required_fields = [
        "budget_amount",
        "protein_target",
        "protein_consumed",
        "food_type"
    ]

    for field in required_fields:
        if state.get(field) is None:
            return "missing"

    return "complete"

get_addresses = None
get_restaurant = None
get_restaurant_menu = None
search_menu = None
update_cart = None
get_cart = None
place_order = None

llm_search = ChatOllama(model = "qwen3:1.7B")
class search_query(BaseModel):
    search_query:str = Field(description= "store only the generated query from the llm default None")


system_prompt3 = """
You are a restaurant search query generator.

Your task is to generate a single restaurant-focused search query that can be used to find relevant restaurants on a food delivery platform.

Rules:

1. Return exactly one search query.
2. Return only plain text.
3. Do not return JSON.
4. Do not return markdown.
5. Do not explain your reasoning.
6. Do not return complete sentences.
7. Do not return multiple queries.
8. Always generate a restaurant-oriented query.
9. Always end the query with the word "restaurant".
10. Focus only on the primary food intent from the user's request.
11. Ignore budget constraints.
12. Ignore protein targets.
13. Ignore protein deficits.
14. Ignore calorie goals.
15. Ignore nutritional calculations.
16. Ignore prices.
17. Use the food type preference when available.
18. If non-vegetarian is requested, prefer terms such as:
    - chicken
    - kebab
    - grilled chicken
    - biryani
    - tandoori chicken
19. If vegetarian is requested, prefer terms such as:
    - paneer
    - soy chaap
    - veg biryani
    - dosa
    - idli
20. Output must be suitable for restaurant discovery, not menu item discovery.

Examples:

User: Need 40g protein, non-vegetarian
Output:
chicken restaurant

User: High protein non-veg food
Output:
kebab restaurant

User: Need vegetarian protein-rich food
Output:
paneer restaurant

User: I want biryani
Output:
biryani restaurant

User: I want dosa
Output:
dosa restaurant

Return only the search query.
"""

llm_with_structure3 = llm_search.with_structured_output(search_query)


async def food_search(state: AgentState):
    budget = state["budget_amount"]
    query = state["user_query"]

    addresses_response = await get_addresses.ainvoke({})
    print(addresses_response)

    address_text = addresses_response[0]["text"]

    match = re.search(r"ID:\s*([a-zA-Z0-9]+)", address_text)

    if match is None:
        raise Exception("No address ID found.")

    address_id = match.group(1)

    print(f"Using Address ID: {address_id}")

    restaurant_query: search_query = llm_with_structure3.invoke(
        [
            SystemMessage(content=system_prompt3),
            HumanMessage(content=query)
        ]
    )

    restaurants = await get_restaurant.ainvoke({
        "query": restaurant_query.search_query,
        "addressId": address_id
    })

    restaurant_text = restaurants[0]["text"]

    restaurant_ids = re.findall(
        r"ID:\s*(\d+)",
        restaurant_text
    )

    top_five_res = restaurant_ids[:2]

    menus = []

    for res_id in top_five_res:
        menu = await get_restaurant_menu.ainvoke({
            "addressId": address_id,
            "restaurantId": int(res_id)
        })

        menus.append({
            "restaurant_id": res_id,
            "menu": menu
        })
    food_pattern = r"- (.*?) — ₹(\d+) \| (Veg|Non-veg).*?\(ID:\s*(\d+)\)"

    items = []

    for entry in menus:

        res_id = entry["restaurant_id"]
        text = entry["menu"][0]["text"]

        matches = re.findall(food_pattern, text)

        for name, price, food_type, item_id in matches:
            items.append({
            "name": name.strip(),
            "price": int(price),
            "food_type": food_type.strip(),
            "restaurant_id": res_id,
            "item_id": int(item_id)
        })
    print(f"Found {len(items)} food items")
    print("\nSEARCH RESULTS")
    print(len(items))
    print(items[:5])

    return {
        "search_results": items,
        "address_id": address_id
    }
def budget_food_type_node(state: AgentState):

    budget = state["budget_amount"]
    food_items = state["search_results"]
    food_type = state["food_type"]

    filtered = []

    for item in food_items:

        item_type = item["food_type"].lower().strip()

        if item_type == "veg":
            item_type = "vegetarian"

        elif item_type == "non-veg":
            item_type = "non_vegetarian"

        if food_type is not None and item_type != food_type:
            continue

        if budget is not None and item["price"] > budget:
            continue

        filtered.append(item)

    print("\nBUDGET FILTER")
    print(len(filtered))
    print(filtered[:5])

    return {
        "budget_food_type_filtered": filtered
    }

def Nutrition_node(state: AgentState):
    filtered = state["budget_food_type_filtered"]

    foods_with_nutrition = []

    for usda_food in filtered:

        try:

            params = {
                "query": usda_food["name"],
                "api_key": api_key
            }

            response = requests.get(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                params=params,
                timeout=10
            )

            if response.status_code != 200:
                print(f"\nUSDA API ERROR ({response.status_code})")
                print(usda_food["name"])
                print(response.text)
                continue

            try:
                data = response.json()
            except Exception:
                print("\nInvalid JSON returned by USDA")
                print(usda_food["name"])
                print(response.text)
                continue

            if "foods" not in data or len(data["foods"]) == 0:
                print(f"No USDA match -> {usda_food['name']}")
                continue

            selected_food = None

            for food in data["foods"]:
                if food.get("dataType") == "Survey (FNDDS)":
                    selected_food = food
                    break

            if selected_food is None:
                for food in data["foods"]:
                    if food.get("dataType") == "SR Legacy":
                        selected_food = food
                        break

            if selected_food is None:
                for food in data["foods"]:
                    if food.get("dataType") == "Branded":
                        selected_food = food
                        break

            if selected_food is None:
                selected_food = data["foods"][0]

            nutrients = selected_food.get("foodNutrients", [])

            protein = 0
            calories = 0
            fat = 0
            carbs = 0

            for nutrient in nutrients:

                name = nutrient.get("nutrientName", "")
                value = nutrient.get("value", 0)

                if name == "Protein":
                    protein = value

                elif name == "Energy":
                    calories = value

                elif name == "Total lipid (fat)":
                    fat = value

                elif name == "Carbohydrate, by difference":
                    carbs = value

            item = usda_food.copy()

            item["protein"] = protein
            item["calories"] = calories
            item["fat"] = fat
            item["carbs"] = carbs

            foods_with_nutrition.append(item)

        except Exception as e:
            print(f"\nNutrition lookup failed for: {usda_food['name']}")
            print(e)
            continue

    print("\nWITH NUTRITION")
    print(len(foods_with_nutrition))
    print(foods_with_nutrition[:5])

    return {
        "foods_with_nutrition": foods_with_nutrition
    }

def protein_deficit(state: AgentState):
    target = state["protein_target"]
    consumed = state["protein_consumed"]

    deficit = max(target-consumed , 0)

    return {"protein_deficit" : deficit}
def Recommendation_node(state: AgentState):

    foods = state["foods_with_nutrition"]
    protein_deficit = state["protein_deficit"]

    for food in foods:

        if protein_deficit == 0:
            coverage = 1
        else:
            coverage = min(food["protein"] / protein_deficit, 1)

        if food["price"] > 0:
            protein_per_rupee = food["protein"] / food["price"]
        else:
            protein_per_rupee = 0

        score = (
            coverage * 100
            + protein_per_rupee * 20
            - food["calories"] * 0.02
            - food["fat"] * 0.5
        )

        food["score"] = score

    foods.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    recommended_foods = foods[:3]
    print("\nFINAL RECOMMENDATION")
    print(len(recommended_foods))
    print(recommended_foods)
    return {
        "recommendation": recommended_foods
    }
def RecommendationDisplay_node(state):
    recommended_foods = state["recommendation"]

    response = "Here are the best food options for you:\n\n"
    print("\n========== RECOMMENDATION ==========")
    print(recommended_foods)
    print("Length:", len(recommended_foods))
    print("===================================\n")

    for i, food in enumerate(recommended_foods, start=1):
        response += (
            f"{i}. {food['name']}\n"
            f"💪 Protein: {food['protein']} g\n"
            f"🔥 Calories: {food['calories']} kcal\n"
            f"💰 Price: ₹{food['price']}\n\n"
        )

    response += (
        "Reply with the option number you want to order.\n"
        "Example:\n"
        "- Option 2\n"
        "- I want the first one\n"
        "- Give me Chicken Biryani"
    )

    choice = interrupt(response)

    return {
    "user_selection": choice
    }

def FoodSelection_node(state):

    query = state["user_selection"].strip().lower()
    recommended_foods = state["recommendation"]

    selected_food = None

    match = re.search(r"\d+", query)

    if match:
        option = int(match.group())

        if 1 <= option <= len(recommended_foods):
            selected_food = recommended_foods[option - 1]

    if selected_food is None:

        for food in recommended_foods:

            food_name = food["name"].lower().strip()

            if (
                query == food_name
                or query in food_name
                or food_name in query
            ):
                selected_food = food
                break

    if selected_food is None:

        return {
            "assistant_response":
            "❌ I couldn't identify which food you selected.\n"
            "Please reply with:\n"
            "- Option number (Example: 2)\n"
            "- Or the exact food name."
        }

    print("\n===== SELECTED FOOD =====")
    print(selected_food)
    print("=========================\n")

    return {
        "selected_food": selected_food,
        "restaurant_id": selected_food["restaurant_id"]
    }
async def search_select_food(state: AgentState):
    selected_food = state["selected_food"]

    print("\n===== USING EXISTING ITEM ID =====")
    print(selected_food)
    print("=================================\n")

    return {
        "menu_item_id": selected_food["item_id"]
    }

async def UpdatecartNode(state: AgentState):
    restaurant_id = state["restaurant_id"]
    address_id = state["address_id"]
    menu_id = state["menu_item_id"]

    cart_response = await update_cart.ainvoke({
        "restaurantId": int(restaurant_id),
        "cartItems": [{
            "menu_item_id": int(menu_id),
            "quantity": 1
        }],
        "addressId": address_id
    })

    print("\n========== UPDATE CART ==========")
    print(cart_response)
    print("=================================\n")

    return {
        "cart_response": cart_response
    }

async def getCartNode(state:AgentState):
    address_id = state["address_id"]
    cart = await get_cart.ainvoke({
        "addressId" : address_id
    })


    print("\n========== CART ==========")
    print(cart)
    print("==========================\n")
    
    return {"cart" : cart}
def ConfirmOrdernode(state:AgentState):
    cart = state["cart"]
    user_response = interrupt(
        f"""
Your cart is ready.

{cart}

Would you like me to place the order?

Reply:
- Yes
- No
"""
    )

    return {
        "confirmation_response": user_response
    }
class OrderConfirmation(BaseModel):
    confirm: bool


system_prompt_confirm = """
Determine whether the user wants to place the order.

Return:

confirm = true

if the user says:
Yes
Y
Go ahead
Proceed
Place it
Order it
Confirm

confirm = false

if the user says:
No
Cancel
Stop
Don't order
Not now

Return only the structured output.
"""

llm_confirm = ChatOllama(model="qwen3:4b")

llm_confirm_structure = llm_confirm.with_structured_output(OrderConfirmation)

def ConfirmDecisionNode(state: AgentState):

    response = llm_confirm_structure.invoke(
        [
            SystemMessage(content=system_prompt_confirm),
            HumanMessage(content=state["confirmation_response"])
        ]
    )

    return {
        "confirm": response.confirm
    }
async def placingOrder(state:AgentState):
    address_id = state["address_id"]
    placed_order = await place_order.ainvoke({
        "addressId" : address_id
    })
    return {"placed_order" : placed_order}

def order_router(state):

    if state["confirm"]:
        return "placingOrder"

    return END


async def create_builder():

    global get_addresses
    global get_restaurant
    global get_restaurant_menu
    global search_menu
    global update_cart
    global get_cart
    global place_order

    oauth_provider = create_oauth_provider("https://mcp.swiggy.com/food")

    client = MultiServerMCPClient({
        "swiggy-food": {
            "url": "https://mcp.swiggy.com/food",
            "transport": "streamable_http",
            "auth": oauth_provider,
        },
    })

    tools = await client.get_tools()

    get_addresses = next(t for t in tools if t.name == "get_addresses")
    get_restaurant = next(t for t in tools if t.name == "search_restaurants")
    get_restaurant_menu = next(t for t in tools if t.name == "get_restaurant_menu")
    search_menu = next(t for t in tools if t.name == "search_menu")
    update_cart = next(t for t in tools if t.name == "update_food_cart")
    get_cart = next(t for t in tools if t.name == "get_food_cart")
    place_order = next(t for t in tools if t.name == "place_food_order")

    builder = StateGraph(AgentState)

    builder.add_node("constraint_extract", constraint_extract)
    builder.add_node("Missing_constraint", Missing_constraint)
    builder.add_node("food_search", food_search)
    builder.add_node("budget_food_type_filter", budget_food_type_node)
    builder.add_node("Nutrition", Nutrition_node)
    builder.add_node("protein_deficit", protein_deficit)
    builder.add_node("Recommendation_node", Recommendation_node)
    builder.add_node("RecommendationDisplay_node", RecommendationDisplay_node)
    builder.add_node("FoodSelection_node", FoodSelection_node)
    builder.add_node("search_select_food", search_select_food)
    builder.add_node("UpdatecartNode", UpdatecartNode)
    builder.add_node("getCartNode", getCartNode)
    builder.add_node("ConfirmOrdernode", ConfirmOrdernode)
    builder.add_node("ConfirmDecisionNode", ConfirmDecisionNode)
    builder.add_node("placingOrder", placingOrder)


    builder.add_edge(START, "constraint_extract")

    builder.add_conditional_edges(
        "constraint_extract",
        constraint_router,
        {
            "missing": "Missing_constraint",
            "complete": "food_search",
        }
    )

    builder.add_edge("Missing_constraint", "constraint_extract")

    builder.add_edge("food_search", "budget_food_type_filter")
    builder.add_edge("budget_food_type_filter", "Nutrition")
    builder.add_edge("Nutrition", "protein_deficit")
    builder.add_edge("protein_deficit", "Recommendation_node")
    builder.add_edge("Recommendation_node", "RecommendationDisplay_node")
    builder.add_edge("RecommendationDisplay_node", "FoodSelection_node")

    # NEW FLOW
    builder.add_edge("FoodSelection_node", "search_select_food")
    builder.add_edge("search_select_food", "UpdatecartNode")

    builder.add_edge("UpdatecartNode", "getCartNode")
    builder.add_edge("getCartNode", "ConfirmOrdernode")
    builder.add_edge("ConfirmOrdernode", "ConfirmDecisionNode")

    builder.add_conditional_edges(
        "ConfirmDecisionNode",
        order_router,
        {
            "placingOrder": "placingOrder",
            END: END,
        }
    )

    builder.add_edge("placingOrder", END)

    return builder
    