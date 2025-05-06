import os
import json
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import httpx
import mysql.connector

app = Flask(__name__)

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="123456",
    database="shopbott"
)

cursor = db.cursor(dictionary=True)

client = OpenAI(
    api_key=""
)

cursor.execute("SELECT item, context, vendor FROM items")
rows = cursor.fetchall()
user_preferences = {
    "default_vendor": "Amazon",
    "item_history": {row['item'].lower(): {"context": row['context'], "vendor": row['vendor']} for row in rows}
}

print("User Preferences: ", user_preferences)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add-item', methods=['POST'])
def add_item():
    user_input = request.form['speech']

    prompt = f"""
    From the following user input: '{user_input}', according to items, extract list of structured JSON data like this:
    [{{"item": ..., "context": ..., "vendor": ...}}].
    Here, context should be one of 'Work' or 'Home'. You need to decide this item is for work or home.
    If vendor is not mentioned, infer from usual vendors like Amazon or Walmart. I need only list of json data without any extra explanation, quotation or symbols (ex: ', ` etc).
    """

    completion = client.chat.completions.create(
        messages=[
            {'role': 'system', 'content': 'You are ShopBott'},
            {'role': 'user', 'content': prompt}
        ],
        model="gpt-4o",
        temperature=0.5
    )
    try:
        json_output = completion.choices[0].message.content
        print(json_output)
        parsed = json.loads(json_output)

        work_items = []
        home_items = []
        conflicts = []

        for entry in parsed:
            item = entry.get("item", "").lower()
            context = entry.get("context", "Unknown").lower()
            print("context", context)
            vendor = entry.get("vendor", "Amazon")

            existing_vendor = user_preferences["item_history"].get(item, {}).get("vendor")

            if existing_vendor and existing_vendor.lower() != vendor.lower():
                conflicts.append({
                    "item": item,
                    "context": context,
                    "old_vendor": existing_vendor,
                    "new_vendor": vendor
                })
                continue

            if "work" in context:
                context = "work"
                work_items.append({"item": item, "context": context, "vendor": vendor})
            elif "home" in context:
                context = "home"
                home_items.append({"item": item, "context": context, "vendor": vendor})

            cursor.execute("SELECT * FROM items WHERE item = %s", (item,))
            existing = cursor.fetchone()

            if not existing:
                cursor.execute(
                    "INSERT INTO items (item, context, vendor) VALUES (%s, %s, %s)",
                    (item, context, vendor)
                )
                db.commit()
            print("work items", work_items)
            print("home items", home_items)

        return jsonify({
            "message": "Item processed.",
            "work_items": work_items,
            "home_items": home_items,
            "conflicts": conflicts
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/resolve-conflict', methods=['POST'])
def resolve_conflict():
    work_items = []
    home_items = []
    data = request.json
    item = data['item'].lower()
    vendor = data['vendor']
    context = data['context'].lower()

    cursor.execute("SELECT * FROM items WHERE item = %s", (item,))
    existing = cursor.fetchone()

    if not existing:
        cursor.execute("INSERT INTO items (item, context, vendor) VALUES (%s, %s, %s)",
                       (item, context, vendor))
    else:
        cursor.execute("UPDATE items SET vendor = %s, context = %s WHERE item = %s",
                       (vendor, context, item))

    db.commit()
     # Fetch the updated lists of work and home items
    cursor.execute("SELECT * FROM items WHERE item = %s", (item,))
    rows = cursor.fetchall()
    print('-=-=-=-=-=-', rows)
    for row in rows:
        if row['Context'].lower() == 'work':
            work_items.append({"item": row["Item"], "context": row["Context"], "vendor": row["Vendor"]})
        if row['Context'].lower() == 'home':
            home_items.append({"item": row["Item"], "context": row["Context"], "vendor": row["Vendor"]})

    return jsonify({
        "message": "Conflict resolved.",
        "work_items": work_items,
        "home_items": home_items
    })

@app.route('/get-items')
def get_items():
    cursor.execute("SELECT item, context, vendor FROM items")
    rows = cursor.fetchall()
    work_items = [row for row in rows if row['Context'].lower() == 'work']
    home_items = [row for row in rows if row['Context'].lower() == 'home']
    print(work_items, "+++++++++++++++++", home_items)
    return jsonify({"work_items": work_items, "home_items": home_items})

if __name__ == '__main__':
    HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
    ssl_context=('fullchain.pem', 'privkey.pem')
    try:
        PORT = int(os.environ.get("SERVER_PORT", "443"))
    except ValueError:
        PORT = 1234
    app.secret_key = "1cd6f35db029d4b8fc98fc05c9efd06a2e2cd1ffc3774d3f035ebd8d"
    app.run(HOST, PORT, debug=False, ssl_context=ssl_context)