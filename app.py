from flask import Flask, request, render_template_string
from industry6 import SmartOutfitRecommender, register_user, authenticate_user, set_user_preferences

app = Flask(__name__, static_url_path='/wardrobe', static_folder='wardrobe')

WARDROBE_PATH = "wardrobe.json"
recommender = SmartOutfitRecommender(WARDROBE_PATH)

# Updated minimal HTML template
html_form = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Outfit Recommender</title>
    <style>
        body { font-family: Arial; margin: 30px; background: #f0f0f0; }
        input, select { width: 300px; padding: 8px; margin-top: 5px; }
        label { display: block; margin-top: 15px; font-weight: bold; }
        button { padding: 10px 20px; margin-top: 20px; font-weight: bold; }
        .result-box { margin-top: 30px; padding: 20px; background: white; border-radius: 10px; border: 1px solid #ccc; }
        .outfit { margin-top: 20px; padding: 10px; background: #f9f9f9; border: 1px solid #aaa; border-radius: 8px; }
        img { height: 100px; border-radius: 6px; margin-right: 10px; margin-top: 5px; }
    </style>
</head>
<body>
    <h1>Smart Outfit Recommender</h1>
    <form method="post" action="/get_recommendation">
        <label>Username:<br><input type="text" name="username" required></label>
        <label>Password:<br><input type="password" name="password" required></label>
        <label>Gender:<br>
            <select name="gender" required>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="unisex">Unisex</option>
            </select>
        </label>
        <label>Age Group:<br>
            <select name="age_group" required>
                <option value="toddler">Toddler</option>
                <option value="teen">Teen</option>
                <option value="adult" selected>Adult</option>
                <option value="senior">Senior</option>
            </select>
        </label>
        <label>Prompt:<br><input type="text" name="prompt" required></label>
        <button type="submit">Get Recommendations</button>
    </form>

    {% if result %}
    <div class="result-box">
        <h2>Your Prompt</h2>
        <p><strong>{{ result['original_prompt'] }}</strong></p>

        <h2>Recommended Outfits</h2>
        {% for outfit in result['outfits'] %}
        <div class="outfit">
            <p><strong>Type:</strong> {{ outfit['type'] }}</p>
            <ul style="list-style: none;">
                {% for item in outfit['items'] %}
                <li>
                    <strong>{{ item['name'] }}</strong> – <em>{{ item['category'] }}</em><br>
                    <img src="/wardrobe/{{ item['image'].split('/')[-1] }}" alt="{{ item['name'] }}">
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endfor %}
    </div>
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET'])
def home():
    return render_template_string(html_form)

@app.route('/get_recommendation', methods=['POST'])
def get_recommendation():
    username = request.form.get("username")
    password = request.form.get("password")
    gender = request.form.get("gender")
    age_group = request.form.get("age_group")
    prompt = request.form.get("prompt")

    try:
        register_user(username, password, {
            "age_group": age_group,
            "gender": gender
        })
    except ValueError:
        set_user_preferences(username, {
            "age_group": age_group,
            "gender": gender
        })

    if not authenticate_user(username, password):
        return render_template_string(html_form + "<p style='color:red;'>Invalid credentials</p>")

    try:
        result = recommender.recommend_outfits(prompt, username)
        result['original_prompt'] = prompt  # Show exactly what user typed
        return render_template_string(html_form, result=result)
    except Exception as e:
        return f"<p>Error: {str(e)}</p>", 500

if __name__ == '__main__':
    app.run(debug=True)
