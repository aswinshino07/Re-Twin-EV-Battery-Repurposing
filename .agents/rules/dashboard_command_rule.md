# Dashboard Command Rule

When the user requests "run on dashboard", "open dashboard", "show dashboard", or "run dashboard":
1. Automatically check if `serve_dashboard.py` is running on port 8050, and start it if needed.
2. Immediately launch `http://localhost:8050/dashboard.html` in the default browser using `powershell -Command "Start-Process 'http://localhost:8050/dashboard.html'"`.
3. Do NOT present multiple choice prompts or ask for clarification. Execute the action immediately and confirm to the user that the dashboard is open.
