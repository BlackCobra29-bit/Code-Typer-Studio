SAMPLES = {
    "Rust struct": {
        "language": "rust",
        "code": """struct User {
    name: String,
    age: u8,
}

impl User {
    fn new(name: &str, age: u8) -> Self {
        Self { name: name.to_string(), age }
    }

    fn greet(&self) {
        println!("Hello, my name is {}.", self.name);
    }
}

fn main() {
    let user = User::new("Cot", 25);
    user.greet();
}""",
    },
    "React component": {
        "language": "tsx",
        "code": """import { useState } from "react";

export function Counter() {
  const [count, setCount] = useState(0);

  return (
    <button onClick={() => setCount(count + 1)}>
      Count: {count}
    </button>
  );
}""",
    },
    "Python API": {
        "language": "python",
        "code": """from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id, "name": "Mira"}""",
    },
    "JavaScript async": {
        "language": "javascript",
        "code": """async function loadProfile(userId) {
  const response = await fetch(`/api/users/${userId}`);

  if (!response.ok) {
    throw new Error("Could not load profile");
  }

  return response.json();
}""",
    },
}

