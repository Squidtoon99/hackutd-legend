from langchain.agents.middleware import TodoListMiddleware


class TodoMiddleware(TodoListMiddleware):
    """Middleware to handle todo list management."""

    async def process_todo_list(self, todo_list: list) -> list:
        # Custom processing of the todo list can be added here
        print("Processing todo list:", todo_list)
        return await super().process_todo_list(todo_list)
