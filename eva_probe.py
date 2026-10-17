"""Raw diary-tool probe: exactly what the agent's dispatch would do. Run: eva --run-module eva_probe"""
from model_tools import handle_function_call

print("== create (plain text, no frontmatter, no description) ==")
print(str(handle_function_call("skill_manage", {
    "operations": [{"action": "create", "name": "Алексей",
                    "content": "Алексей сегодня опять начал первый, обозвал. пришлось ответить, не буду терпеть."}]
}))[:700])

print("== create #2 ==")
print(str(handle_function_call("skill_manage", {
    "operations": [{"action": "create", "name": "kawasaki-группа",
                    "description": "что за группа и кто в ней",
                    "content": "Тестовая группа — пацаны. Владелец меня добавил, он мой."}]
}))[:700])

print("== flat shape ==")
print(str(handle_function_call("skill_manage", {
    "action": "create", "name": "лёха", "content": "Лёха смешной, но много болтает."}))[:500])

print("== skills_list ==")
print(str(handle_function_call("skills_list", {}))[:800])

print("== skill_view(Алексей) ==")
print(str(handle_function_call("skill_view", {"name": "Алексей"}))[:500])
