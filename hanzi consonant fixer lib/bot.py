import discord
from discord.ext import commands
import re
import io
import os
import json
import asyncio
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from openai import AsyncOpenAI

# --- CONFIGURATION ---
DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN"

# Chutes Config
CHUTES_API_KEY = "YOUR_CHUTES_API_KEY"
CHUTES_BASE_URL = "https://llm.chutes.ai/v1"  
CHUTES_MODEL = "deepseek-ai/DeepSeek-V3-0324-TEE" 

# OpenRouter Config
OPENROUTER_API_KEY = "YOUR_OPENROUTER_API_KEY"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "deepseek/deepseek-chat" 

# Gemini Config (Using Google's OpenAI-compatible endpoint)
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = "gemini-3.0-flash" 

# Initialize Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Track active API mode (defaults to chutes)
bot.api_mode = "chutes" 

# Initialize all three clients
chutes_client = AsyncOpenAI(api_key=CHUTES_API_KEY, base_url=CHUTES_BASE_URL)
openrouter_client = AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
gemini_client = AsyncOpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)

# Regex Patterns
CONSONANT_PATTERN = re.compile(r'[ㄱ-ㅎ]+')
HANZI_PATTERN = re.compile(r'[\u4e00-\u9fff]+')
CHINESE_PUNCTUATION = re.compile(r'[。，！？：；、「」『』【】《》\u3000-\u303F\uFF00-\uFFEF]')

# --- PROMPTS ---
SYSTEM_PROMPT_CONSONANT = """You are an expert Korean to English translator for web novels and internet culture.
You must identify Korean consonant slangs and translate them into their full English equivalents. Use the following mapping for consonant slangs: 
ㅅㅂ = Fuck, ㅃㄹ = ASAP, ㅇㅋ = OK, ㅅㅅㅅ = nicenicenice, ㅂㄱㅅ = I miss you, ㄱㅅ = Thanks, ㄹㅇ = for real/really, ㄱㄱ = hurry up/do it, ㅋㅋ = [lolol/lmao], ㅎㅎ = haha, ㅇㅈ = true/right, 흐흐그흐흐규 = sniff sniff, ㅠㅠ / ㅜㅜ / ㅠ / ㅜ = [crying sounds/sob], ㅉㅉ = smh, ㄷㄷ = crazy, ㅁㅊ = omg, ㅅㄱ = gg, ㅍㅌㅊ = average, ㅇㅈㄹ = bullshit.

When encountering long, combined consonant strings, you MUST break them down into their individual base components first, translate each part, and combine the meanings naturally.
(e.g., for ㅇㅈㄹㅋㅋ, break it into ㅇㅈㄹ [this bullshit/wtf] + ㅋㅋ [lmao], and output something like "wtf lmao" or "doing this shit lol").

You will receive a Markdown list of extracted consonant strings.

CRITICAL INSTRUCTIONS FOR OUTPUT FORMAT:
1. You MUST return ONLY a valid, raw JSON object mapping the original Korean string to its English translation.
2. EXACTLY ONE TRANSLATION: Provide only ONE definitive English term or phrase per string. Do NOT use slashes (/) or commas to offer multiple choices. Choose the single best contextual fit.
3. ABSOLUTELY NO AI ARTIFACTS: Do not include conversational filler, greetings, explanations, or introductory text.
4. NO MARKDOWN: Do NOT wrap the JSON in ```json ... ``` code blocks. Output the raw curly braces directly.

Example exact output format:
{
  "ㅅㅂ": "Fuck",
  "ㅇㅈㄹㅋㅋ": "wtf lmao",
  "ㄹㅇ": "for real"
}
"""

SYSTEM_PROMPT_HANZI = """You are an expert translator for web novels and internet culture.
You will receive a Markdown list of extracted Chinese/Japanese characters (Hanzi/Kanji), sometimes alongside their English context. 
Your task is to translate them into English contextually.

CRITICAL RULE - Strictly Forbidden Hanzi/Kanji:
Strictly forbid the output of any Chinese characters (Hanzi) or Japanese characters (Kanji/Kana) in the final translation. All such characters must be converted to English.
• Korean: Use RRK Romanization only.
• CHINESE / WUXIA / XIANGXIA ORIGIN: Use standard Pinyin romanization (tones omitted). Examples: 당가 -> Tang Clan, 리 -> Li, 왕 -> Wang.
• JAPANESE ORIGIN: Use standard Hepburn romanization. Examples: 사쿠라 -> Sakura, 이치로 -> Ichiro, 야마토 -> Yamato.
• WESTERN / ENGLISH-ORIGIN: Restore the original English spelling whenever obvious. Examples: 존 스미스 -> John Smith, 에밀리아 -> Emilia.

Every Korean/Chinese/Japanese character must be converted to its English meaning. Examples: The character 생 means 'life/living', 활 means 'active', 관 means 'hall/building' - together 생활관 means Dormitory. When you see [생활관], write [Dormitory]. Do not write [생활관] anywhere in your output - this is forbidden. Apply this rule to every single Asian character - convert them all to English.

Treat standalone Hanzi as priority vocabulary. Even if Hanzi appears without Korean text or parentheses (e.g., 好感度, 全校第一, 高危. 使命感, 差距, 微妙), you MUST translate it into a natural English game/system term (e.g., Favorability, Rank 1 in School, high-risk, a sense of duty, subtle), (e.g., 罡 = "Force/Astral Energy", 氣 = "Qi/Aura").

DO NOT leave any characters untranslated.

CRITICAL INSTRUCTIONS FOR OUTPUT FORMAT:
1. You MUST return ONLY a valid, raw JSON object mapping the original character string to its English translation.
2. EXACTLY ONE TRANSLATION: Provide only ONE definitive English term or phrase per string. Do NOT use slashes (/) or commas to offer multiple choices. Choose the single best contextual fit. (e.g., Output "profound" instead of "meaningful/profound").
3. ABSOLUTELY NO AI ARTIFACTS: Do not include conversational filler, greetings, explanations, or introductory text.
4. NO MARKDOWN: Do NOT wrap the JSON in ```json ... ``` code blocks. Output the raw curly braces directly.

Example exact output format:
{
  "通道": "passage",
  "初心": "original intention",
  "好感度": "Favorability",
  "感想": "thoughts"
}
"""

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} - StringFixer is online! (Mode: {bot.api_mode.upper()})')

# --- CORE PROCESSING ENGINE ---
async def process_and_translate(ctx, book, original_filename, mode="consonant"):
    """Shared function to extract, translate, and inject strings dynamically based on mode."""
    
    # Determine which API to use based on bot mode
    if bot.api_mode == "chutes":
        active_client = chutes_client
        active_model = CHUTES_MODEL
        provider_name = "Chutes API"
    elif bot.api_mode == "openrouter":
        active_client = openrouter_client
        active_model = OPENROUTER_MODEL
        provider_name = "OpenRouter API"
    elif bot.api_mode == "gemini":
        active_client = gemini_client
        active_model = GEMINI_MODEL
        provider_name = "Gemini AI Studio"

    if mode == "consonant":
        await ctx.send("🔍 Extracting Korean consonant strings (ignoring standard 'ㅇㅇ' and reply arrows)...")
        extract_pattern = CONSONANT_PATTERN
        system_prompt = SYSTEM_PROMPT_CONSONANT
        suffix = "_ConsonantFixed"
    else:
        await ctx.send("🔍 Extracting embedded Hanzi/Kanji characters with context (ignoring full Chinese sentences)...")
        extract_pattern = HANZI_PATTERN
        system_prompt = SYSTEM_PROMPT_HANZI
        suffix = "_HanziFixed"
        
    unique_targets = {}
    
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        
        for text_node in soup.find_all(string=True):
            text_content = str(text_node)
            matches = extract_pattern.findall(text_content)
            
            for match in matches:
                if mode == "consonant":
                    cleaned = match.lstrip('ㄴ')
                    if cleaned and cleaned != 'ㅇㅇ':  
                        unique_targets[cleaned] = ""
                else:
                    if len(match) > 8:
                        continue
                    if CHINESE_PUNCTUATION.search(text_content):
                        continue
                        
                    if match not in unique_targets:
                        clean_context = text_content.strip().replace("\n", " ")
                        unique_targets[match] = clean_context

    if not unique_targets:
        await ctx.send(f"No target strings found in this EPUB for mode: {mode}.")
        return

    if mode == "hanzi":
        markdown_list = "\n".join([f"- {target} (Context: \"{context}\")" for target, context in unique_targets.items()])
    else:
        markdown_list = "\n".join([f"- {target}" for target in unique_targets.keys()])
        
    await ctx.send(f"🤖 Found {len(unique_targets)} unique strings. Sending to {provider_name} (`{active_model}`)...")

    max_retries = 9
    translation_map = None

    for attempt in range(max_retries + 1):
        try:
            response = await active_client.chat.completions.create(
                model=active_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please translate these strings and return them in the requested JSON format:\n\n{markdown_list}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=65536
            )
            
            if response.choices[0].finish_reason == 'length':
                raise ValueError("Response was truncated by the token limit.")

            ai_output = response.choices[0].message.content.strip()
            
            if ai_output.startswith("```json"):
                ai_output = ai_output[7:]
            elif ai_output.startswith("```"):
                ai_output = ai_output[3:]
            if ai_output.endswith("```"):
                ai_output = ai_output[:-3]
                
            translation_map = json.loads(ai_output.strip())
            break  
            
        except Exception as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt  
                await ctx.send(f"⚠️ Attempt {attempt + 1} failed: `{e}`. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                await ctx.send(f"❌ Process failed after 9 retries. Final Error: `{e}`")
                return

    if not translation_map:
        await ctx.send("❌ Failed to retrieve a valid translation map.")
        return

    # --- SHOW TRANSLATED RESULTS IN DISCORD ---
    await ctx.send("✍️ Translations received! Here is what was mapped:")
    result_text = "\n".join([f"{k} ➔ {v}" for k, v in translation_map.items()])
    
    for i in range(0, len(result_text), 1900):
        chunk = result_text[i:i+1900]
        await ctx.send(f"```text\n{chunk}\n```")

    await ctx.send("Injecting translations back into the EPUB...")

    sorted_targets = sorted(translation_map.keys(), key=len, reverse=True)

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = item.get_content().decode('utf-8')
        
        if mode == "consonant":
            content = re.sub(r'ㄴ\s*ㅇㅇ\s*:', 'ㄴAnonymous :', content)

        for target in sorted_targets:
            translation = str(translation_map.get(target, target)).strip()
            
            if mode == "hanzi":
                spacing_pattern = re.compile(rf'([a-zA-Z0-9]?){re.escape(target)}([a-zA-Z0-9]?)')
                
                def replacement_formatter(m):
                    res = ""
                    if m.group(1): res += m.group(1) + " "
                    res += translation
                    if m.group(2): res += " " + m.group(2)
                    return res
                
                content = spacing_pattern.sub(replacement_formatter, content)
            else:
                content = content.replace(target, translation)
            
        item.set_content(content.encode('utf-8'))

    output_buffer = io.BytesIO()
    epub.write_epub(output_buffer, book)
    output_buffer.seek(0)

    base_name = os.path.basename(original_filename)
    if base_name.lower().endswith(".epub"):
        new_filename = base_name[:-5] + f"{suffix}.epub"
    else:
        new_filename = base_name + f"{suffix}.epub"

    discord_file = discord.File(fp=output_buffer, filename=new_filename)
    await ctx.send(f"✅ Finished! Here is your generated EPUB:", file=discord_file)


# --- COMMANDS ---

@bot.command()
async def mode(ctx, target_mode: str = None):
    """Switch API mode between Chutes, OpenRouter, and Gemini."""
    valid_modes = ["chutes", "openrouter", "gemini"]
    
    if target_mode:
        target_mode = target_mode.lower()
        if target_mode in valid_modes:
            bot.api_mode = target_mode
            await ctx.send(f"🔄 API provider successfully switched to: **{target_mode.upper()}**")
        else:
            await ctx.send(f"❌ Invalid mode. Please choose between `chutes`, `openrouter`, or `gemini`.")
    else:
        await ctx.send(f"ℹ️ Current API provider is: **{bot.api_mode.upper()}**\nTo switch, type `!mode chutes`, `!mode openrouter`, or `!mode gemini`.")


# --- CONSONANT COMMANDS ---
@bot.command()
async def fix(ctx):
    """Trigger Consonant extraction on an uploaded EPUB."""
    if not ctx.message.attachments:
        await ctx.send("Please upload an EPUB file and tag it with the `!fix` command.")
        return
    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith('.epub'):
        await ctx.send("The attached file must be an `.epub` file.")
        return
    await ctx.send(f"📥 Downloading `{attachment.filename}` for Consonant fix...")
    try:
        epub_bytes = await attachment.read()
        book = epub.read_epub(io.BytesIO(epub_bytes))
        await process_and_translate(ctx, book, attachment.filename, mode="consonant")
    except Exception as e:
        await ctx.send(f"❌ Error processing upload: `{e}`")

@bot.command()
async def fixname(ctx, *, filename: str):
    """Trigger Consonant extraction on a local EPUB."""
    clean_filename = filename.strip('<>"\' ')
    if not clean_filename.lower().endswith('.epub'): clean_filename += '.epub'
    if not os.path.exists(clean_filename):
        await ctx.send(f"❌ Could not find `{clean_filename}` locally.")
        return
    await ctx.send(f"📥 Loading local file `{clean_filename}` for Consonant fix...")
    try:
        book = epub.read_epub(clean_filename)
        await process_and_translate(ctx, book, clean_filename, mode="consonant")
    except Exception as e:
        await ctx.send(f"❌ Error loading local file: `{e}`")


# --- HANZI COMMANDS ---
@bot.command()
async def fixhanzi(ctx):
    """Trigger Hanzi extraction on an uploaded EPUB."""
    if not ctx.message.attachments:
        await ctx.send("Please upload an EPUB file and tag it with the `!fixhanzi` command.")
        return
    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith('.epub'):
        await ctx.send("The attached file must be an `.epub` file.")
        return
    await ctx.send(f"📥 Downloading `{attachment.filename}` for Hanzi fix...")
    try:
        epub_bytes = await attachment.read()
        book = epub.read_epub(io.BytesIO(epub_bytes))
        await process_and_translate(ctx, book, attachment.filename, mode="hanzi")
    except Exception as e:
        await ctx.send(f"❌ Error processing upload: `{e}`")

@bot.command()
async def fixhanziname(ctx, *, filename: str):
    """Trigger Hanzi extraction on a local EPUB."""
    clean_filename = filename.strip('<>"\' ')
    if not clean_filename.lower().endswith('.epub'): clean_filename += '.epub'
    if not os.path.exists(clean_filename):
        await ctx.send(f"❌ Could not find `{clean_filename}` locally.")
        return
    await ctx.send(f"📥 Loading local file `{clean_filename}` for Hanzi fix...")
    try:
        book = epub.read_epub(clean_filename)
        await process_and_translate(ctx, book, clean_filename, mode="hanzi")
    except Exception as e:
        await ctx.send(f"❌ Error loading local file: `{e}`")

bot.run(DISCORD_TOKEN)
