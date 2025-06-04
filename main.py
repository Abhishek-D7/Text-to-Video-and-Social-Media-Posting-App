from pydantic import BaseModel, Field
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import FastAPI

#Connect to MongoDB locally
MONGO_URL = "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URL)
db = client.library
book_collection = db.books

#Create the app
app = FastAPI()
from fastapi import FastAPI, HTTPException

#Pydantic model for input
class Book(BaseModel):
    title: str
    author: str
    year: int
    book_id: int

#Pydantic model for DB return with alias
class BookDB(Book):
    id: str  # _id from MongoDB, converted to string

#Helper to convert MongoDB doc to dict
def book_helper(book) -> dict:
    return {
        "id": str(book["_id"]),
        "title": book["title"],
        "author": book["author"],
        "year": book["year"],
        "book_id": book["book_id"]
    }

#Add new book
@app.post("/books_add", response_model=BookDB)
async def add_books(book: Book):
    result = await book_collection.insert_one(book.dict())
    created_book = await book_collection.find_one({"_id": result.inserted_id})
    return book_helper(created_book)

#Get all books
@app.get("/books", response_model=List[BookDB])
async def get_all_books():
    print("Hit")
    books = []
    async for book in book_collection.find():
        books.append(book_helper(book))
    return books

#Get book by ID
@app.get("/books/{book_id}", response_model=BookDB)
async def get_book_by_id(book_id: int):
    book = await book_collection.find_one({"book_id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book_helper(book)

#Update book
@app.put("/books_update/{book_id}", response_model=BookDB)
async def update_book(book_id: int, update_book: Book):
    result = await book_collection.update_one(
        {"book_id": book_id},
        {"$set": update_book.dict()}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    book = await book_collection.find_one({"book_id": book_id})
    return book_helper(book)

#Delete book
@app.delete("/books_delete/{book_id}")
async def delete_book(book_id: int):
    result = await book_collection.delete_one({"book_id": book_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"message": "Book deleted successfully"}

