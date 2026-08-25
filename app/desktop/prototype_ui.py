from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

# Theme Colors
NAVY = "#0A192F"
SLATE = "#F8FAFC"
EMERALD = "#10B981"

HTML_CONTENT = f"""
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background-color: {SLATE}; color: {NAVY}; font-family: sans-serif; }}
        .bg-navy {{ background-color: {NAVY}; }}
        .text-emerald {{ color: {EMERALD}; }}
        .bg-emerald {{ background-color: {EMERALD}; }}
    </style>
</head>
<body class="flex h-screen">
    <aside class="w-64 bg-navy text-white p-6">
        <h1 class="text-2xl font-bold mb-10">Apex Finance</h1>
        <nav class="space-y-4">
            <a href="#" class="block p-2 rounded bg-white/10">Dashboard</a>
            <a href="#" class="block p-2">Students</a>
            <a href="#" class="block p-2">Reports</a>
        </nav>
    </aside>
    <main class="flex-1 p-8">
        <header class="flex justify-between items-center mb-8">
            <h2 class="text-3xl font-semibold">Dashboard</h2>
            <button class="bg-emerald text-white px-4 py-2 rounded font-medium">Record Payment</button>
        </header>
        <section class="grid grid-cols-3 gap-6 mb-8">
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
                <p class="text-gray-500">Total Revenue</p>
                <p class="text-2xl font-bold">$124,500</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
                <p class="text-gray-500">Outstanding</p>
                <p class="text-2xl font-bold text-red-500">$8,200</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
                <p class="text-gray-500">Active Students</p>
                <p class="text-2xl font-bold">1,204</p>
            </div>
        </section>
        <section class="bg-white p-6 rounded-lg shadow-sm border border-gray-100">
            <h3 class="text-xl font-semibold mb-4">Recent Transactions</h3>
            <table class="w-full text-left">
                <thead class="text-gray-500">
                    <tr><th class="pb-3">Student</th><th class="pb-3">Amount</th><th class="pb-3">Date</th></tr>
                </thead>
                <tbody class="divide-y">
                    <tr><td class="py-3">John Doe</td><td class="py-3">$500</td><td class="py-3">Aug 22</td></tr>
                    <tr><td class="py-3">Jane Smith</td><td class="py-3">$750</td><td class="py-3">Aug 21</td></tr>
                </tbody>
            </table>
        </section>
    </main>
</body>
</html>
"""

@app.get("/")
async def get_dashboard():
    return HTMLResponse(content=HTML_CONTENT)

if __name__ == "__main__":
    print("Running Apex Finance Prototype at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
