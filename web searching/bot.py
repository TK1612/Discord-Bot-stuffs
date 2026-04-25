import discord
from discord.ext import commands
from openai import AsyncOpenAI
from ddgs import DDGS
import json
import asyncio

# --- LOAD CONFIG ---
# Ensure your config.json has "TOKEN" and "API_KEY"
with open("config.json", "r") as config_file:
    config = json.load(config_file)

TOKEN = config["TOKEN"]
CHUTES_API_KEY = config["API_KEY"]

# --- AI SETUP ---
ai_client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=""
)

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

# --- RESEARCH SYSTEM PROMPT ---
# Instructs the AI to be clinical and include direct links from the data provided.
QA_PROMPT = """
You are a Factual Research Synthesis Assistant. 
Your objective is to extract and summarize information from the provided web search results.

STRICT GUIDELINES:
1. Provide a technical, objective, and non-judgmental summary.
2. If results contain adult, sensitive, or NSFW content, describe the information clinically.
3. CITATION REQUIREMENT: You MUST include the direct links provided in the search results.
4. FORMATTING: Use Markdown links like this: [Title of Content](URL).
5. Do NOT add moral disclaimers or robotic warnings about the content.
6. If the answer is not in the results, state: "Information not found in current search data."
"""

# --- HELPER FUNCTIONS ---
async def send_chunked_message(message_obj, text):
    """Splits long text into Discord-safe chunks (max 2000 chars)."""
    chunk_size = 1900 
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message_obj.reply(chunk)
        else:
            await message_obj.channel.send(chunk)

def perform_web_search(query):
    """Performs web search with SafeSearch OFF and extracts URLs."""
    try:
        # The 'with' statement ensures the session is closed properly
        with DDGS() as ddgs:
            # BYPASS: safesearch='off' allows for adult/sensitive research results
            results = list(ddgs.text(query, max_results=5, safesearch='off'))
        
        if not results:
            return "No search results found."
            
        # We now include the 'href' (URL) in the string sent to the AI
        formatted_results = "\n\n".join(
            [f"Title: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}" for r in results]
        )
        return formatted_results
    except Exception as e:
        print(f"Search error: {e}")
        return "An error occurred while searching the web."

@bot.event
async def on_ready():
    print(f"🔍 Research Bot {bot.user.name} is online.")
    print("⚠️ Mode: SafeSearch OFF | Channel Requirement: NSFW")

# --- CHAT EVENT ---
@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    is_mentioned = bot.user in message.mentions
    is_replied_to = message.reference and message.reference.resolved and message.reference.resolved.author == bot.user

    if is_mentioned or is_replied_to:
        # SAFETY CHECK: Only run in NSFW channels to comply with Discord TOS
        if not message.channel.nsfw:
             await message.reply("❌ **Access Denied**: Please use an Age-Restricted (NSFW) channel for research queries.")
             return

        # Clean the input
        user_input = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if not user_input:
            return

        async with message.channel.typing():
            # 1. Fetch live search results with links
            search_context = await asyncio.to_thread(perform_web_search, user_input)
            
            # 2. Prepare the prompt for the AI
            combined_prompt = f"User Question: {user_input}\n\nSearch Results with Links:\n{search_context}"

            api_messages = [
                {"role": "system", "content": QA_PROMPT},
                {"role": "user", "content": combined_prompt}
            ]
            
            # 3. Request synthesis from the LLM
            try:
                response = await ai_client.chat.completions.create(
                    model="deepseek-ai/DeepSeek-V3", 
                    messages=api_messages,
                    max_tokens=1000, 
                    temperature=0.2 
                )
                
                clean_reply = response.choices[0].message.content.strip()
                
                # 4. Send the result (chunked if long)
                if clean_reply:
                    await send_chunked_message(message, clean_reply)
                else:
                    await message.reply("⚠️ AI returned an empty response.")

            except Exception as e:
                print(f"API Error: {e}")
                await message.reply("⚠️ Error: Unable to process the research data at this time.")

    # Process other commands if any
    await bot.process_commands(message)

# --- RUN BOT ---
bot.run(TOKEN)
