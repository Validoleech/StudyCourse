import requests, os, uuid, time
from fastapi import HTTPException
from dotenv import load_dotenv
from auth.models import TokenResponse
from fastapi import APIRouter

router = APIRouter()


load_dotenv()

AUTHORIZATION_KEY = os.getenv("AUTHORIZATION_KEY")
SCOPE = os.getenv("GIGACHAT_SCOPE")

if not AUTHORIZATION_KEY or not SCOPE:
    raise ValueError("AUTHORIZATION_KEY or GIGACHAT_SCOPE not found in .env file.")

token_data = {
    "access_token": None,
    "expires_in": 1800,
    "expires_at": 0
}

def get_new_token(authorization_key: str, scope: str, RqUID: str) -> str:
    """Получение нового токена."""

    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

    payload = {
        'scope': scope
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': RqUID,
        'Authorization': f'Basic {authorization_key}'
    }

    response = requests.post(url, headers=headers, data=payload, verify=False)

    if response.status_code == 200:
        token_data["access_token"] = response.json().get('access_token')
        token_data["expires_at"] = time.time() + token_data.get("expires_in", 0) - 60
        print(f"Access Token: {token_data["access_token"]}")
    else:
        print(f"Error: {response.status_code}, {response.text}")
        raise HTTPException(status_code=500, detail="Failed to retrieve GigaChat API access token.")

def is_token_valid() -> bool:
    """Проверка валидности токена."""

    if token_data["access_token"] and time.time() < token_data["expires_at"]:
        # Проверяем токен через вызов доступных моделей
        url = "https://gigachat.devices.sberbank.ru/api/v1/models"
        headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token_data["access_token"]}'
        }
        try:
            response = requests.get(url, headers=headers, verify=False)
            if response.status_code == 200:
                print("Token is valid")
                return True
            else:
                print("Token is invalid, update required")
                return False

        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            return False

    return False

def get_token() -> str | None:
    """Возвращает действующий токен."""

    RqUID = str(uuid.uuid4())

    if not is_token_valid():
        get_new_token(AUTHORIZATION_KEY, SCOPE, RqUID)
    
    return token_data["access_token"]

# Ручка для получения токена
@router.get("/token", response_model=TokenResponse)
async def get_gigachat_access_token():
    """Ручка для получения токена GigaChat."""
    token = get_token()
    if token:
        return {"access_token": token}
    else:
        raise HTTPException(status_code=500, detail="Could not retrieve a valid GigaChat token.")