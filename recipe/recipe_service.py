from typing import List, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import requests
import time
from urllib3.exceptions import InsecureRequestWarning
from recipe.models import FoodRequest, RecipeResponse, StringResponse, IngredientRequest, Ingredient

router = APIRouter()

TOKEN_SERVICE_URL = "http://localhost:9000/token"

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Ай-ай-ай так делать…
def get_gigachat_token() -> str:
    """Получает токен для доступа к GigaChat API из сервиса токенов за MAX_RETRIES попыток."""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(TOKEN_SERVICE_URL, verify=False)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access_token")
            if access_token:
                return access_token
            else:
                print(f"Recipe Service: Token service response missing 'access_token'. Attempt: {attempt + 1}/{MAX_RETRIES}")
        except requests.exceptions.RequestException as e:
            print(f"Recipe Service: Error retrieving token from service (attempt {attempt + 1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY_SECONDS)

    raise HTTPException(status_code=500, detail="Failed to retrieve GigaChat token from the token service after multiple retries.")

def get_gigachat_recipe_response(food: FoodRequest) -> requests.Response:
    blacklist = {"teapot"} # Глупый блеклист для экономии токенов
    if food.food in blacklist:
        raise HTTPException(status_code=418, detail="I'm a teapot")
    if not food.food.strip():
        raise HTTPException(status_code=400, detail="Food must be a non-empty string")

    token = get_gigachat_token()

    context = "Ты профессиональный шеф-повар. Отвечай лаконично и не отклоняйся от задачи."

    prompt = f"Создай и напиши список ингредиентов для приготовления этого блюда: {food}, в формате JSON. В ответе не должно быть ничего, кроме JSON-текста. Список продуктов должен быть лаконичен.\n" \
             "У JSON-ответа должна быть следующая структура:\n" \
             '{"recipe": ["шаг 1", "шаг 2", …] "ingredients": [{"name": "ингредиент1", "amount": "количество"}, {"name": "ингредиент2", "amount": "количество"}, ...]}.'

    payload = json.dumps({
        "model": "GigaChat-Max",
        "messages": [
            {
                "role": "system",
                "content": context
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False,
        "update_interval": 0
    })
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions", headers=headers, data=payload, verify=False)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Recipe Service: Error communicating with GigaChat API (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    raise HTTPException(status_code=500, detail=f"Error communicating with GigaChat API after multiple retries.")

def parse_gigachat_answer(response: requests.Response) -> RecipeResponse:

    try:

        response_json = response.json()

        content = response_json.get("messages", [])[-1].get("content")
        recipe_data_from_gigachat = json.loads(content)
        # Вытаскиваем контент из ответа…
        content = recipe_data_from_gigachat['choices'][0]['message']['content'] 
        # И распихиваем его в RecipeResponse
        return RecipeResponse(
            recipe=content.get("recipe", []),
            ingredients=[Ingredient(**item) for item in content.get("ingredients", [])]
        )
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="GigaChat response content is not valid JSON.")
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"GigaChat response content is missing expected key: {e}")
    except TypeError:
        raise HTTPException(status_code=500, detail="GigaChat response content has an unexpected structure.")

@router.get("/recipe", response_model=RecipeResponse)
def generate_recipe(food: FoodRequest):
    """Генерация рецепта блюда."""
    response = get_gigachat_recipe_response(food) # Получаем .json ответ от GigaChat
    response = parse_gigachat_answer(response) # Вытаскиваем из него recipe и ingredients. Сделано вслепую — сайт сбера перестал отвечать, постман крутит вечно
    response["ingredients"] = get_kuper_ingredient(response["ingredients"]) # Вмешиваем гиперссылки на продукты
    return

@router.get("/recipe/link", response_model=StringResponse)
def get_kuper_ingredient(request_body: IngredientRequest) -> str:

    ingredient = request_body.ingredient

    url = "https://eda.yandex.ru/api/v1/menu/search"

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru",
        "content-type": "application/json;charset=UTF-8",
    }

    # Хардкод…
    payload = json.dumps({
        "region_id": 1,
        "place_slug": "perekrestok",
        "text": ingredient,
        "location": {
            "lat": 55.7106035,
            "lon": 37.743341
        }
    })

    try:
        response = requests.post(url, headers=headers, data=payload, verify=False)
        data = response.json()
        link = f"https://eda.yandex.ru/retail/perekrestok?item={data['blocks'][0]['payload']['products'][0]['public_id']}" # Берём самый первый попавшийся продукт
        return StringResponse(result=create_markdown_link(ingredient, link))
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Yandex.Eda API: {e}")

def create_markdown_link(text: str, link: str) -> str:
    "Создаём markdown-ссылку."
    return f"[{link}]({text})"

def recipe_to_markdown(recipe_response: RecipeResponse) -> str:
    markdown = ""
    markdown += "## Рецепт\n\n"
    for i, step in enumerate(recipe_response.recipe, start=1):
        markdown += f"{i}. {step}\n\n"
    markdown += "\n\n\n\n"
    markdown += "### Ингредиенты\n\n"
    for ingredient in recipe_response.ingredients:
        markdown += f"- {ingredient.name} | {ingredient.amount}\n"
