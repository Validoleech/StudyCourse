from pydantic import BaseModel

class FoodRequest(BaseModel):
    food: str

class RecipeResponse(BaseModel):
    recipe: str
    ingredients: list[str]

class StringResponse(BaseModel):
    result: str

class IngredientRequest(BaseModel):
    ingredient: str