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
llm = ChatOllama(model = "qwen2.5:1.5b")


class extract(BaseModel):
    amount : float|None  = Field(description ="extract the amount from the user input default value is none")
    protein_target : float|None = Field(description = "extract the target protein from the user input default value is none")
    protein_consumed : float|None = Field(description = "extract the consumed protein from the user query default value is none")
    food_type: str | None = Field(
    description="Extract the food type (vegetarian or non_vegetarian). Default is None."
)
system_prompt = """
You are a constraint extraction AI.

Extract the following fields from the user's query:

1. amount
   - Budget amount mentioned by the user.

2. protein_target
   - Desired protein intake in grams.

3. protein_consumed
   - Protein already consumed by the user in grams.

4. food_type
   - User's food preference.
   - Return:
     - "vegetarian" if the user explicitly mentions veg, vegetarian, pure veg.
     - "non_vegetarian" if the user explicitly mentions non veg, non-veg, chicken, fish, egg, meat, etc.
   - If not mentioned, return None.

Rules:
- Extract only information explicitly stated by the user.
- Never infer, estimate, or guess values.
- If a field is not mentioned, return None.
- If the query contains no relevant information, return None for all fields.
- Do not perform calculations.
- Do not assume that every number refers to every field.
- Do not infer vegetarian or non-vegetarian preference from budget alone.
- Standardize food_type values as:
  - vegetarian
  - non_vegetarian

Examples:

User: "I have ₹300"
amount = 300
protein_target = None
protein_consumed = None
food_type = None

User: "Need 120g protein"
amount = None
protein_target = 120
protein_consumed = None
food_type = None

User: "I've already consumed 40g protein"
amount = None
protein_target = None
protein_consumed = 40
food_type = None

User: "Veg food under 200"
amount = 200
protein_target = None
protein_consumed = None
food_type = vegetarian

User: "Non veg food under 300"
amount = 300
protein_target = None
protein_consumed = None
food_type = non_vegetarian

User: "Need 30g protein, non veg, budget 250"
amount = 250
protein_target = 30
protein_consumed = None
food_type = non_vegetarian

User: "Recommend food"
amount = None
protein_target = None
protein_consumed = None
food_type = None
"""
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


class followup(BaseModel):

    question : str
system_prompt2 = """
You are a follow-up question generation assistant.

Your task is to generate a natural question asking the user only for the missing information.

Possible missing information:
- budget → user's spending limit
- protein_target → desired protein intake in grams
- food_type → vegetarian or non-vegetarian preference

Rules:
- Ask only for the missing information provided.
- Do not ask for information that is already available.
- If multiple pieces of information are missing, combine them into a single concise question.
- Use natural, conversational language.
- For food_type, ask whether the user prefers vegetarian or non-vegetarian food.
- For protein_target, ask how much protein the user wants.
- For budget, ask for the user's budget.
- Keep the question short and clear.
- Do not explain your reasoning.
- Do not return anything except the question.
"""

def Missing_constraint(state:AgentState):
    missing = []

    if state["budget_amount"] is None:
        missing.append("budget")

    if state["protein_target"] is None:
        missing.append("protein_target")
    if state['food_type'] is None:
        missing.append("food_type")
    if not missing:
        return {
            "missing_constraints": [],
            "follow_up_question": None
        }
    
    llm_with_structure2 = llm.with_structured_output(followup)
    
    response: followup = llm_with_structure2.invoke(
        [
            SystemMessage(content=system_prompt2),
               HumanMessage(
    content=f"""
    The user has not provided the following information:

    {', '.join(missing)}

    Generate a follow-up question asking only for this information.
"""
)
            ])
        
    answer = interrupt(response.question)

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

llm_search = ChatOllama(model = "qwen2.5:7b")
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
    print(restaurant_text)

    restaurant_ids = re.findall(
        r"ID:\s*(\d+)",
        restaurant_text
    )

    top_five_res = restaurant_ids[:5]

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

    food_pattern = r" - (.*?) — ₹(\d+) \| (Veg|Non-veg)"

    items = []

    for entry in menus:
        print(entry["menu"])
        res_id = entry["restaurant_id"]
        text = entry["menu"][0]["text"]

        matches = re.findall(food_pattern, text)
        print(matches)
        for name, price, food_type in matches:

            items.append({
                "name": name,
                "price": int(price),
                "food_type": food_type,
                "restaurant_id": res_id
            })

    return {
        "search_results": items,
        "address_id": address_id
    }
def budget_food_type_node(state:AgentState):
    budget = state["budget_amount"]
    food_items = state["search_results"]
    food_type = state['food_type']
    if budget is None:
        filtered = [
        item
        for item in food_items
        if item["food_type"] == food_type
    ]
        
    else :
        filtered = [
        item for item in food_items
        if item['price']<= budget and 
        item['food_type'] ==  food_type
        
    ]
    return {"budget_food_type_filtered" : filtered}
def Nutrition_node(state: AgentState):
    filtered = state["budget_food_type_filtered"]
    foods_with_nutrition = []
    for usda_food in filtered:
        params= {
        "query" : usda_food["name"],
        "api_key" : api_key 
        }
        response = requests.get(
        "https://api.nal.usda.gov/fdc/v1/foods/search",
        params=params
        )
        data = response.json()
        if "foods" not in data or len(data["foods"]) == 0:
            continue

        selected_food = None

        for food in data["foods"]:
            if food["dataType"] == "Survey (FNDDS)":
                selected_food = food
                break

        if selected_food is None:
            for food in data["foods"]:
                if food["dataType"] == "SR Legacy":
                    selected_food = food
                    break

        if selected_food is None:
            for food in data["foods"]:
                if food["dataType"] == "Branded":
                    selected_food = food
                    break

        if selected_food is None:
            selected_food = data["foods"][0]
        
    
        nutrients = selected_food["foodNutrients"]
        protein = 0
        calories = 0
        fat = 0
        carbs = 0

        for nutrient in nutrients:

            if nutrient["nutrientName"] == "Protein":
                protein = nutrient["value"]

            elif nutrient["nutrientName"] == "Energy":
                calories = nutrient["value"]

            elif nutrient["nutrientName"] == "Total lipid (fat)":
                fat = nutrient["value"]

            elif nutrient["nutrientName"] == "Carbohydrate, by difference":
                carbs = nutrient["value"]

        usda_food["protein"] = protein
        usda_food["calories"] = calories
        usda_food["fat"] = fat
        usda_food["carbs"] = carbs

        foods_with_nutrition.append(usda_food)

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

    return {
        "recommendation": recommended_foods
    }
def RecommendationDisplay_node(state):
    recommended_foods = state["recommendation"]

    response = "Here are the best food options for you:\n\n"

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

system_prompt_food = """"You are an information extraction assistant.

Your job is to extract the food selection from the user's message.

You will receive:

1. The user's message.
2. The list of recommended food options.

Extract only the following fields:

* option_number:
  The option number selected by the user, if mentioned (e.g. "option 2", "the third one", "number 5").

* food_name:
  The exact food name if the user mentions the food instead of the option number.

Rules:

* Return only structured data matching the provided schema.
* Do not explain your reasoning.
* If the user selects by option number, fill `option_number` and leave `food_name` as null.
* If the user selects by food name, fill `food_name` and leave `option_number` as null.
* If the user does not clearly choose any food, return null for both fields.
* Match food names only from the provided recommended food list.

Examples:

User: "Order option 2"
→ option_number = 2
→ food_name = null

User: "I'll take the grilled chicken."
→ option_number = null
→ food_name = "Grilled Chicken"

User: "I want the first one."
→ option_number = 1
→ food_name = null

User: "Give me the biryani."
→ option_number = null
→ food_name = "Chicken Biryani"
"""
class UserSelection(BaseModel):
    option_number: int = Field(description="extract the option number if the user mentioned in the prompt default none")
    food_name: str = Field(description="extract the food_name if it is there in the user prompt default none")
llm_food_selection = ChatOllama(model = "qwen3:4b")
llm_with_structure4 = llm_food_selection.with_structured_output(UserSelection)


def FoodSelection_node(state):

    query = state["user_selection"]
    recommended_foods = state["recommendation"]

    selection = llm_with_structure4.invoke(
        [
            SystemMessage(content=system_prompt_food),
            HumanMessage(
                content=f"""
        Recommended Foods:

    {recommended_foods}

    User Message:

    {query}
    """
            ),
        ]
    )

    selected_food = None

    if selection.option_number:

        option = selection.option_number

        if 1 <= option <= len(recommended_foods):
            selected_food = recommended_foods[option - 1]

    elif selection.food_name:

        for food in recommended_foods:

            if food["name"].lower() == selection.food_name.lower():

                selected_food = food
                break

    return {
        "selected_food": selected_food,
        "restaurant_id": selected_food["restaurant_id"]
    }
async def search_select_food(state:AgentState):
    selected_food = state["selected_food"]
    restaurant_id = state["restaurant_id"]
    address_id = state["address_id"]

    result = await search_menu.ainvoke({
        "query": selected_food["name"],
        "restaurantId": restaurant_id,
        "addressId": address_id
})
    return {"selected_menu" : result}

def CustomizationSelection_node(state: AgentState):
    selected_menu = state["selected_menu"]
    menu_text = selected_menu[0]["text"]
    match = re.search(r"ID:\s*(\d+)", menu_text)

    menu_item_id = match.group(1) if match else None
    has_customization = (
        "Addons (" in menu_text
        or "Variants" in menu_text
        or "customisation" in menu_text.lower()
    )

    if has_customization:

        question = (
            "This item has customization options.\n\n"
            "Please choose the add-ons or variants you want.\n\n"
            f"{menu_text}"
        )

        return {
            "follow_up_question": question,
            "menu_item_id": menu_item_id
        }

    return {
        "menu_item_id": menu_item_id
    }
async def UpdatecartNode(state:AgentState):
    restaurant_id = state["restaurant_id"]
    address_id = state["address_id"]
    menu_id = state["menu_item_id"]

    cart_response = await update_cart.ainvoke({
        'restaurantId' : restaurant_id,
        'cartItems' : [{
            "menu_item_id": menu_id,
            "quantity": 1
        }],
        'addressId' : address_id
        
    })

    return {"cart_response" : cart_response}
async def getCartNode(state:AgentState):
    address_id = state["address_id"]
    cart = await get_cart.ainvoke({
        "addressId" : address_id
    })
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
        return "PlaceOrder"

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


    builder.add_node("constraint_extract" , constraint_extract )
    builder.add_node("Missing_constraint" , Missing_constraint)
    builder.add_node("food_search" , food_search)
    builder.add_node("budget_food_type_filter" , budget_food_type_node)
    builder.add_node("Nutrition" , Nutrition_node)
    builder.add_node("protein_deficit" ,  protein_deficit)
    builder.add_node("Recommendation_node" , Recommendation_node)
    builder.add_node("RecommendationDisplay_node" , RecommendationDisplay_node)
    builder.add_node("FoodSelection_node" , FoodSelection_node)
    builder.add_node("search_select_food" , search_select_food)
    builder.add_node("CustomizationSelection_node" , CustomizationSelection_node)
    builder.add_node("UpdatecartNode" , UpdatecartNode)
    builder.add_node("getCartNode" , getCartNode)
    builder.add_node("ConfirmOrdernode" , ConfirmOrdernode)
    builder.add_node("ConfirmDecisionNode" , ConfirmDecisionNode)
    builder.add_node("placingOrder" , placingOrder)


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
    builder.add_edge("FoodSelection_node", "search_select_food")
    builder.add_edge("search_select_food", "CustomizationSelection_node")
    builder.add_edge("CustomizationSelection_node", "UpdatecartNode")
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