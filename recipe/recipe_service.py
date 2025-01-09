from fastapi import APIRouter, HTTPException
from recipe.models import RecipeResponse, FoodRequest, StringResponse, IngredientRequest
import json
import requests

router = APIRouter()


TOKEN_SERVICE_URL = "http://localhost:9000/token"

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1

def get_gigachat_token():
    # Ай-ай-ай, так делать…
    """Получает токен для доступа к GigaChat API из сервиса токенов."""
    try:
        response = requests.get(TOKEN_SERVICE_URL, verify=False)
        response.raise_for_status()
        token_data = response.json()
        return token_data.get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Recipe Service: Error retrieving token from service: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve GigaChat token from the token service.")

def get_gigachat_recipe_response(food: FoodRequest):
    # Здесь стоило иметь чёрный список из слов (или других символов), которые точно не являются едой. Так как количество токенов в день у юзера ограничено, подобное ограничение позволило бы их сэкономить.
    if food == "teapot":
        raise HTTPException(status_code=418, detail="Я чайник")
    if food == "":
        raise HTTPException(status_code=400, detail="Food cannot be empty")

    token = get_gigachat_token()

    context = f"Ты профессиональный шеф-повар. Отвечай лаконично и не отклоняйся от задачи." \

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
    try:
        response = requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions", headers=headers, data=payload, verify=False)
        response.raise_for_status()  # Поднять исключение, если статус ответа не 200
        return response
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with GigaChat API: {e}")

def parse_gigachat_answer(content: str) -> RecipeResponse:
    """Парсит гигачатовский ответ в модель RecipeRespon."""
    try:
        recipe_data_from_gigachat = json.loads(content)
        return RecipeResponse(
            recipe="\n".join(recipe_data_from_gigachat.get("recipe", [])),
            ingredients=recipe_data_from_gigachat.get("ingredients", [])
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
    response = get_gigachat_recipe_response(food) # Получаем ответ от GigaChat
    response = parse_gigachat_answer(response) # Преобразуем ответ в JSON
    #response = ingredients_to_kuper(response["ingredients"])
    # Конвертировать в markdown
    return parse_gigachat_answer(response.json().get("messages")[-1].get("content"))



@router.get("/recipe/link", response_model=StringResponse)
def get_kuper_ingredient(request_body: IngredientRequest) -> str:

    ingredient = request_body.ingredient

    url = "https://eda.yandex.ru/api/v1/menu/search"

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru",
        "content-type": "application/json;charset=UTF-8",
    }

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
        response = requests.post(url, headers=headers, data=payload)
        data = response.json()
        link = f"https://eda.yandex.ru/retail/perekrestok?item={data['blocks'][0]['payload']['products'][0]['public_id']}"
        return StringResponse(result=create_markdown_link(ingredient, link))
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Yandex.Eda API: {e}")

def create_markdown_link(text: str, link: str) -> str:
    "Создаём markdown-ссылку."
    return f"[{link}]({text})"