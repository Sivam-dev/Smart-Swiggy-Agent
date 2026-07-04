# 🍽️ Swiggy Nutrition Agent

An **Agentic AI Food Ordering Assistant** built using **LangGraph**, **LangChain**, **Ollama**, and **Swiggy MCP** that recommends food based on nutritional goals and budget, then places an order through Swiggy using a multi-step AI workflow.

---

# 🚀 Features

- 🧠 Agentic workflow built with LangGraph
- 🤖 LLM-powered constraint extraction
- 👤 Human-in-the-loop (HITL) interactions using LangGraph Interrupts
- 📦 Structured outputs using Pydantic
- 💰 Budget-aware food recommendations
- 🥗 Veg / Non-Veg preference filtering
- 💪 Protein target recommendation system
- 📊 USDA FoodData Central nutrition integration
- ⭐ Intelligent food ranking algorithm
- 🛒 Swiggy restaurant search
- 🍽 Swiggy menu search
- ➕ Automatic cart creation
- ✅ Order confirmation
- 🚚 Order placement

---

# 🏗️ Workflow

```text
User Query
     │
     ▼
Constraint Extraction
     │
     ▼
Missing Constraint Detection
     │
     ▼
Human Follow-up (Interrupt)
     │
     ▼
Restaurant Search
     │
     ▼
Food Filtering
     │
     ▼
Nutrition Lookup (USDA)
     │
     ▼
Protein Deficit Calculation
     │
     ▼
Food Recommendation Engine
     │
     ▼
Recommendation Display
     │
     ▼
Food Selection
     │
     ▼
Swiggy Menu Search
     │
     ▼
Cart Update
     │
     ▼
Cart Review
     │
     ▼
Human Confirmation
     │
     ▼
Place Order
```

---

# ⚙️ Tech Stack

## AI

- LangGraph
- LangChain
- Ollama
- Qwen (3B / 4B)

## APIs

- Swiggy MCP
- USDA FoodData Central API

## Backend

- Python
- AsyncIO
- Requests
- Pydantic

---

# 🧠 Constraint Extraction

The assistant automatically extracts:

- Budget
- Target Protein
- Consumed Protein
- Food Preference

Example:

**Input**

```
I want non veg food under ₹200 with 40 grams protein.
```

**Extracted Constraints**

```
Budget: 200
Protein Target: 40g
Food Type: Non-Veg
```

---

# 👤 Human-in-the-Loop

Whenever required information is missing, the graph pauses execution using **LangGraph Interrupts**.

Example:

```
User:
I want non veg food.
```

↓

```
Assistant:
What is your desired protein intake?
```

The workflow resumes automatically after receiving the user's response.

---

# 🍗 Recommendation Engine

Each food item is enriched with nutritional information using the **USDA FoodData Central API**.

Recommendations consider:

- Protein
- Calories
- Fat
- Carbohydrates
- User Budget
- Food Preference
- Remaining Protein Requirement

Each item is scored using a custom ranking algorithm before being recommended.

---

# 🛒 Swiggy Integration

The assistant can:

- Search Restaurants
- Retrieve Menus
- Search Menu Items
- Add Food to Cart
- Retrieve Cart
- Place Orders

---

# 💬 Example Conversation

```
User:
I want non veg food under ₹200

Assistant:
What is your desired protein intake?

User:
40 grams

Assistant:

1. Chicken Steam Momos
Protein: 22g
Calories: 310 kcal
Price: ₹189

2. Chicken Wrap
Protein: 18g
Calories: 280 kcal
Price: ₹175

Reply with the option number.

User:
Option 1

Assistant:
Your cart is ready.

Would you like to place the order?

User:
Yes

Assistant:
Order placed successfully.
```

---

# 📁 Project Structure

```
.
├── main.py
├── agent.py
├── graph.py
├── prompts.py
├── state.py
├── tools.py
├── requirements.txt
└── README.md
```

---

# 🎯 Concepts Demonstrated

- Agentic AI Systems
- LangGraph State Machines
- Human-in-the-Loop Workflows
- Tool Calling
- Structured Outputs
- Prompt Engineering
- API Integration
- Workflow Orchestration
- Async Programming
- State Management
- Python Backend Development

---

# 🔮 Future Improvements

- FastAPI Backend
- Web Dashboard
- User Authentication
- Persistent Memory
- Meal History
- Multi-Day Meal Planner
- Personalized Recommendations
- Docker Deployment
- Cloud Hosting

---

# 📌 Note

This project was built to explore **real-world Agentic AI workflows** by combining LLM reasoning, workflow orchestration, external API integration, and human approval steps into a practical food recommendation and ordering assistant.

---

# 👨‍💻 Author

**Sivam Singh**

If you found this project interesting, feel free to connect or reach out!
