
import google.generativeai as genai
from tools import *
from config import GEMINI_API_KEY, HARDCODED_PREFIXES

MODEL = "gemini-2.0-flash"

# Configure the Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting
RATE_LIMIT = {}  # user_id: last_request_time
COOLDOWN_SECONDS = 10  # Minimum seconds between requests

# Command-to-Model Mapping with Gemini-specific descriptions
commands = {
    "chat": {
        "description": "General conversational AI responses using Gemini",
        "max_tokens": 100,
        "system_prompt": "You are a helpful Gemini AI assistant."
    },
    "reason": {
        "description": "Step-by-step logical problem-solving with Gemini",
        "max_tokens": 500,
        "system_prompt": "You are a Gemini logical reasoning assistant. Analyze problems step-by-step."
    },
    "summarize": {
        "description": "Condensing text to key points using Gemini",
        "max_tokens": 400,
        "system_prompt": "Summarize the following text concisely while preserving all key information."
    },
    "translate": {
        "description": "Language translation powered by Gemini",
        "max_tokens": 600,
        "system_prompt": "Translate the following text accurately, maintaining the original meaning and tone."
    },
    "code": {
        "description": "Generating or fixing code with Gemini explanations",
        "max_tokens": 1200,
        "system_prompt": "You are a Gemini programming assistant. Generate clear, efficient, and well-commented code."
    },
    "write": {
        "description": "Creating high-quality content with Gemini",
        "max_tokens": 1000,
        "system_prompt": "Create well-structured, engaging content based on the given topic or requirements."
    },
    "analysis": {
        "description": "In-depth data and content analysis using Gemini",
        "max_tokens": 1000,
        "system_prompt": "Analyze the following information in detail, identifying patterns, insights, and implications."
    },
    "answer": {
        "description": "Comprehensive responses to complex queries via Gemini",
        "max_tokens": 100,
        "system_prompt": "Provide accurate, well-researched answers to the following question."
    },
    "complete": {
        "description": "Auto-completing text with Gemini context awareness",
        "max_tokens": 100,
        "system_prompt": "Complete the following text in a natural and contextually appropriate way."
    },
    "extract": {
        "description": "Extracting key information from text using Gemini",
        "max_tokens": 100,
        "system_prompt": "Extract the most important information, data points, and insights from the following text."
    },
}

def split_message(text: str, max_length: int = 4000) -> List[str]:
    """Split long text into chunks while preserving paragraph boundaries."""
    chunks = []
    while text:
        if len(text) > max_length:
            split_at = text.rfind('\n', 0, max_length)
            if split_at == -1:
                split_at = max_length
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        else:
            chunks.append(text)
            break
    return chunks

async def safe_edit(message: Message, text: str):
    """Edit message ignoring MessageNotModified errors"""
    try:
        await message.edit(text)
    except Exception as e:
        logger.error(f"Edit error: {str(e)}")



@Client.on_message(filters.me & filters.command(list(commands.keys()), prefixes="/"))
@retry()
async def ai_handler(client: Client, message: Message):
    user_id = message.from_user.id
    current_time = time.time()
    # Rate limiting check
    if user_id in RATE_LIMIT and current_time - RATE_LIMIT[user_id] < COOLDOWN_SECONDS:
        wait_time = round(COOLDOWN_SECONDS - (current_time - RATE_LIMIT[user_id]))
        await message.edit(f"⏳ Please wait {wait_time}s before another request.")
        return
    RATE_LIMIT[user_id] = current_time
    cmd = message.command[0].lower()
    command_info = commands.get(cmd)
    if not command_info:
        await message.edit(f"❌ Unknown command: {cmd}")
        return
    # Get user input
    user_input = ""
    original_input = ""
    if message.reply_to_message and message.reply_to_message.text:
        user_input = message.reply_to_message.text
    elif len(message.command) > 1:
        user_input = " ".join(message.command[1:])
        original_input = user_input  # Store the original input for later use
    else:
        await message.edit(f"❌ Provide input text or reply to a message.\nUsage: `/{cmd} text`")
        return
    if len(user_input.strip()) < 2:
        await message.edit("❌ Input text too short.")
        return
    processing_message = await message.edit("⏳ Processing your request...")
    spinner_task = None
    response_received = False  # Flag to track response state
    try:
        # Start spinner
        spinner_task = asyncio.create_task(spinner(processing_message))
        # Process request with timeout
        result = await asyncio.wait_for(
            process_gemini_request(
                command_info['system_prompt'],
                user_input,
                command_info['max_tokens']
            ),
            timeout=60
        )
        response_received = True
        # Format response
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        header = f"**🤖 Gemini {cmd.capitalize()} [{timestamp}]**\n\n"

        # Add original input in <pre> tags if it exists and wasn't a reply
        if original_input and not message.reply_to_message:
            full_response = f"{header}<pre>{original_input}</pre>\n\n{result}"
        else:
            full_response = f"{header}{result}"

        # Split and send messages
        chunks = split_message(full_response)
        # Cancel spinner before editing
        if spinner_task and not spinner_task.done():
            spinner_task.cancel()
            try:
                await spinner_task
            except asyncio.CancelledError:
                pass
        # Edit original message with first chunk
        await safe_edit(processing_message, chunks[0])
        # Send remaining chunks as replies
        for chunk in chunks[1:]:
            await processing_message.reply(chunk, quote=True)
    except asyncio.TimeoutError:
        await safe_edit(processing_message, "❌ Request timed out after 60 seconds")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await safe_edit(processing_message, f"❌ Error: {str(e)}")
    finally:
        if spinner_task and not response_received:
            spinner_task.cancel()

async def spinner(message: Message):
    """Animated spinner without elapsed time"""
    indicators = ["⢄", "⢂", "⢁", "⡁", "⡈", "⡐", "⡠"]
    idx = 0
    while True:
        try:
            await safe_edit(message, f"{indicators[idx]} Processing...")
            idx = (idx + 1) % len(indicators)
            await asyncio.sleep(0.8)  # Reduced update frequency
        except asyncio.CancelledError:
            break
        except:
            await asyncio.sleep(1)

async def process_gemini_request(system_prompt, user_input, max_tokens):
    """Handle Gemini AI request with error handling"""
    try:
        # Create a Gemini model instance
        model = genai.GenerativeModel(MODEL)
        
        # For Gemini, we need to combine system prompt and user input
        combined_prompt = f"{system_prompt}\n\nUser input: {user_input}"
        
        # Generate content
        response = await asyncio.to_thread(
            model.generate_content,
            combined_prompt,
            generation_config={"max_output_tokens": max_tokens}
        )
        
        # Extract text from response
        return response.text
    except Exception as e:
        logger.error(f"Gemini API Error: {str(e)}")
        raise e

@Client.on_message(filters.me & filters.command('gemini_help', prefixes=HARDCODED_PREFIXES))
@retry()
async def help_command(client: Client, message: Message):
    help_text = "**🤖 Gemini AI commands:**\n\n"

    for cmd, info in commands.items():
        help_text += f"• `/{cmd}` - {info['description']}\n"

    help_text += "\n**Usage:**\n"
    help_text += "1. Reply to a message: `/command`\n"
    help_text += "2. Direct input: `/command your text here`\n"
    help_text += "\n**Examples:**\n"
    help_text += "• `/summarize` (as reply to a long text)\n"
    help_text += "• `/code write a function to calculate fibonacci numbers`\n"
    help_text += "• `/translate Hello, how are you?`\n"

    await message.edit(help_text)
