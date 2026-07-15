from flask import Flask, render_template, request, jsonify
import os
import json
import logging
from dotenv import load_dotenv
from groq import Groq

# load env file
load_dotenv()


logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# --- API KEY SETUP ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

if GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        app.logger.info("Groq client initialized")
    except Exception as e:
        app.logger.error(f"Failed to init Groq client: {e}")
        client = None
else:
    client = None
    app.logger.warning("GROQ_API_KEY not set")

@app.route('/')
def index():
    """Renders the main HTML page for the communication analyzer."""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_communication():
    """
    Receives text from the frontend, sends it to Groq API for analysis,
    and returns the structured feedback.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400

        user_text = data.get('text', '').strip()
        if not user_text:
            return jsonify({"error": "Please provide text to analyze."}), 400

        # Mock mode for testing without API key
        if not GROQ_API_KEY or client is None:
            if MOCK_MODE or app.debug:
                app.logger.warning("No GROQ_API_KEY - returning MOCK")
                return jsonify({
                    "professionalism": {"rating": "Fair", "feedback": "MOCK MODE: Set GROQ_API_KEY env var. The text is somewhat informal."},
                    "tone": {"overall": "Neutral", "feedback": "MOCK MODE: Tone is direct but could be perceived as demanding."},
                    "clarity": {"rating": "Good", "feedback": "MOCK MODE: Clear but deadline ambiguous."},
                    "etiquette": {"rating": "Fair", "feedback": "MOCK MODE: Missing greeting/closing."},
                    "poor_habits": ["Demanding language (ASAP)", "Missing greeting"],
                    "suggestions": ["Add polite greeting", "Replace ASAP with specific time"]
                }), 200
            return jsonify({"error": "GROQ API Key is not configured. Please set GROQ_API_KEY in .env or as environment variable."}), 500

        # --- PROMPT FOR GROQ ---
        system_prompt = """You are an expert workplace communication analyst.
You must analyze the given email/chat for professionalism, tone, clarity, and etiquette.
Return ONLY a valid JSON object with this exact structure, no markdown, no extra text:

{
  "professionalism": {"rating": "Excellent/Good/Fair/Poor", "feedback": "Detailed feedback"},
  "tone": {"overall": "Positive/Neutral/Negative/Formal/Informal", "feedback": "Detailed feedback"},
  "clarity": {"rating": "Excellent/Good/Fair/Poor", "feedback": "Detailed feedback"},
  "etiquette": {"rating": "Excellent/Good/Fair/Poor", "feedback": "Detailed feedback"},
  "poor_habits": ["List of poor habits"],
  "suggestions": ["List of actionable suggestions"]
}"""

        user_prompt = f"""Analyze this workplace communication:

\"\"\"{user_text}\"\"\"

Remember: Output must be valid JSON only, following the structure defined in system prompt."""

        app.logger.info(f"Calling Groq API with model llama-3.3-70b-versatile, text length: {len(user_text)}")

        # --- GROQ CALL ---
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.3-70b-versatile", 
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"}  
        )

        raw_response = chat_completion.choices[0].message.content
        app.logger.info(f"Groq raw response: {raw_response[:500]}")

        try:
            parsed_analysis = json.loads(raw_response)

            # Validate required keys exist
            required_keys = ["professionalism", "tone", "clarity", "etiquette", "poor_habits", "suggestions"]
            for key in required_keys:
                if key not in parsed_analysis:
                    app.logger.warning(f"Groq response missing key: {key}, filling default")
                    if key in ["poor_habits", "suggestions"]:
                        parsed_analysis[key] = []
                    else:
                        parsed_analysis[key] = {"rating": "N/A", "feedback": "Not provided", "overall": "Neutral"} if key == "tone" else {"rating": "N/A", "feedback": "Not provided"}

            return jsonify(parsed_analysis), 200

        except json.JSONDecodeError as e:
            app.logger.error(f"Groq returned non-JSON: {raw_response}")
            return jsonify({"error": f"AI response was not valid JSON: {str(e)}. Raw: {raw_response[:500]}"}), 500

    except Exception as e:
        # Groq specific errors
        error_str = str(e)
        app.logger.exception(f"Groq API error: {e}")

        # Provide helpful messages for common Groq errors
        if "api_key" in error_str.lower() or "authentication" in error_str.lower() or "401" in error_str:
            return jsonify({"error": f"Groq API Key invalid or missing: {error_str}. Check GROQ_API_KEY in .env"}), 500
        if "rate_limit" in error_str.lower() or "429" in error_str:
            return jsonify({"error": f"Groq rate limit hit: {error_str}. Wait a minute and try again."}), 429
        if "model" in error_str.lower() and "not found" in error_str.lower():
            return jsonify({"error": f"Model not found, try llama-3.1-8b-instant: {error_str}"}), 500

        return jsonify({"error": f"An unexpected error occurred: {error_str}"}), 500

@app.route('/health')
def health():
    """Simple health check"""
    return jsonify({
        "status": "ok",
        "groq_key_configured": bool(GROQ_API_KEY),
        "mock_mode": MOCK_MODE
    })

if __name__ == '__main__':
    if not os.path.exists(os.path.join('templates', 'index.html')):
        print("WARNING: templates/index.html not found! Make sure HTML is in templates/ folder")

    # Print config on startup
    print(f"GROQ_API_KEY configured: {bool(GROQ_API_KEY)}")
    print(f"MOCK_MODE: {MOCK_MODE}")
    if not GROQ_API_KEY:
        print("TIP: Create a .env file with GROQ_API_KEY=your_key_here")
        print("     Or set MOCK_MODE=true for testing without key")

    app.run(host='0.0.0.0', port=5000, debug=True)
