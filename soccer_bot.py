import logging
import asyncio
import os
import requests
import telegram
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import NetworkError, TimedOut
from datetime import datetime
import pytz
from functools import wraps
APPROVE_EMOJI = "✅"
BALL_EMOJI = "⚽"
bringing_ball = set()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"python-telegram-bot version: {telegram.__version__}")

# Fetching the environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GROUP_CHAT_ID = os.environ.get('GROUP_CHAT_ID')

if not BOT_TOKEN:
    logger.error("No BOT_TOKEN environment variable set")
    raise ValueError("No BOT_TOKEN environment variable set")

if not GROUP_CHAT_ID:
    logger.error("No GROUP_CHAT_ID environment variable set")
    raise ValueError("No GROUP_CHAT_ID environment variable set")

logger.info(f"BOT_TOKEN: {BOT_TOKEN[:5]}...")
logger.info(f"GROUP_CHAT_ID: {GROUP_CHAT_ID}")

# Lists for players
playing_list = []
waiting_list = []
MAX_PLAYERS = 15
game_created = False

# Dictionary to track approvals
approvals = {}

def check_internet_connection():
    try:
        requests.get("https://api.telegram.org", timeout=5)
        logger.info("Internet connection is available.")
        return True
    except requests.ConnectionError:
        logger.error("No internet connection available.")
        return False

async def check_telegram_api(bot):
    try:
        await bot.get_me()
        logger.info("Telegram API is responsive.")
        return True
    except Exception as e:
        logger.error(f"Telegram API is not responsive: {e}")
        return False

def private_chat_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type != 'private':
            user = update.effective_user
            await update.message.reply_text(
                f"Hi @{user.username or user.first_name}! Please send commands in a private chat with me."
            )
            return
        return await func(update, context)
    return wrapper

@private_chat_only
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global game_created
    if not game_created:
        await update.message.reply_text("No game has been created yet. Please wait for an admin to create a game.")
        return

    user = update.effective_user
    user_id = user.id
    user_name = user.username or f"{user.first_name}_{user_id}"
    
    if user_name in playing_list or user_name in waiting_list:
        await update.message.reply_text("You're already registered.")
    elif len(playing_list) < MAX_PLAYERS:
        playing_list.append(user_name)
        await update.message.reply_text(f"You've been added to the playing list, {user.first_name}.")
    else:
        waiting_list.append(user_name)
        await update.message.reply_text(f"You've been added to the waiting list, {user.first_name}.")
    
    logger.info(f"Register command used by {user_name}")

@private_chat_only
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global game_created
    if not game_created:
        await update.message.reply_text("No game has been created yet.")
        return
    user = update.effective_user
    user_id = user.id
    user_name = user.username or f"{user.first_name}_{user_id}"
    
    if user_name in playing_list:
        playing_list.remove(user_name)
        await update.message.reply_text(f"You've been removed from the playing list, {user.first_name}.")
        if waiting_list:
            moved_player = waiting_list.pop(0)
            playing_list.append(moved_player)
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, 
                                           text=f"{moved_player} has been moved from the waiting list to the playing list.")
    elif user_name in waiting_list:
        waiting_list.remove(user_name)
        await update.message.reply_text(f"You've been removed from the waiting list, {user.first_name}.")
    else:
        await update.message.reply_text("You're not registered for the game.")
    
    logger.info(f"Remove command used by {user_name}")

@private_chat_only
async def print_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global game_created
    if not game_created:
        await update.message.reply_text("No game has been created yet.")
        return
    message = "Playing List:\n"
    for i, player in enumerate(playing_list, 1):
        approval_status = f"{APPROVE_EMOJI}" if approvals.get(player, False) else ""
        ball_status = f"{BALL_EMOJI}" if player in bringing_ball else ""
        message += f"{i}. @{player} {approval_status}{ball_status}\n"
    message += "\nWaiting List:\n"
    for i, player in enumerate(waiting_list, 1):
        message += f"{i}. @{player}\n"
    await update.message.reply_text(message)
    logger.info(f"Print list command used by @{update.effective_user.username}")

@private_chat_only
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global game_created
    if not game_created:
        await update.message.reply_text("No game has been created yet.")
        return
    user = update.effective_user
    user_id = user.id
    user_name = user.username or f"{user.first_name}_{user_id}"
    
    if user_name in playing_list:
        approvals[user_name] = True
        await update.message.reply_text(f"Your attendance has been approved, {user.first_name}. {APPROVE_EMOJI}")
    else:
        await update.message.reply_text("You're not in the playing list.")
    logger.info(f"Approve command used by {user_name}")

@private_chat_only
async def create_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global playing_list, waiting_list, approvals, bringing_ball, game_created
    playing_list = []
    waiting_list = []
    approvals = {}
    bringing_ball = set()
    game_created = True
    await update.message.reply_text("New game created for Thursday 6:30-8:30 PM. Lists have been reset.")
    logger.info(f"Create game command used by @{update.effective_user.username}")

@private_chat_only
async def clear_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global playing_list, waiting_list, approvals, bringing_ball, game_created
    playing_list = []
    waiting_list = []
    approvals = {}
    bringing_ball = set()
    game_created = False
    await update.message.reply_text("All lists have been cleared. Use /create_game to start a new game.")
    logger.info(f"Clear list command used by @{update.effective_user.username}")

@private_chat_only
async def bring_ball(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global game_created
    if not game_created:
        await update.message.reply_text("No game has been created yet.")
        return
    user = update.effective_user
    user_id = user.id
    user_name = user.username or f"{user.first_name}_{user_id}"
    
    if user_name in playing_list:
        bringing_ball.add(user_name)
        await update.message.reply_text(f"Great, {user.first_name}! We've noted that you're bringing a ball. {BALL_EMOJI}")
    else:
        await update.message.reply_text("You're not in the playing list. Please register for the game first.")
    logger.info(f"Bring ball command used by {user_name}")



async def send_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(pytz.timezone('Asia/Jerusalem'))
    if now.weekday() == 3 and now.hour >= 10 and now.hour < 16:  # Thursday between 10 AM and 4 PM
        unapproved = [player for player in playing_list if player not in approvals]
        if unapproved:
            message = "Reminder: Please approve your attendance before 4 PM. Use the /approve command in a private chat with me.\n"
            for player in unapproved:
                message += f"@{player} "
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message)

@private_chat_only
async def manual_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global game_created
    if not game_created:
        await update.message.reply_text("No game has been created yet.")
        return

    unapproved = [player for player in playing_list if player not in approvals]
    if unapproved:
        message = "Reminder: Please approve your attendance before 4 PM. Use the /approve command in a private chat with the bot.\n"
        for player in unapproved:
            message += f"@{player} "
        
        # Send the reminder to the group chat
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message)
        
        # Confirm to the user in the private chat that the reminder was sent
        await update.message.reply_text("Reminder sent to the group.")
    else:
        await update.message.reply_text("All players have approved their attendance.")
    
    logger.info(f"Manual reminder command used by @{update.effective_user.username}")

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    if chat_type == 'private':
        await update.message.reply_text(f"This private chat ID is: {chat_id}")
    else:
        await update.message.reply_text(f"This {chat_type} chat ID is: {chat_id}")
    logger.info(f"Get chat ID command used by @{update.effective_user.username} in {chat_type} chat")

async def set_commands_with_retry(bot, max_retries=3):
    commands = [
        BotCommand("register", "Register for the game"),
        BotCommand("remove", "Remove yourself from the game"),
        BotCommand("print_list", "Show the current player lists"),
        BotCommand("approve", "Approve your attendance"),
        BotCommand("create_game", "Create a new game and reset lists"),
        BotCommand("clear_list", "Clear all lists"),
        BotCommand("send_reminder", "Manually send a reminder"),
        BotCommand("get_chat_id", "Get the chat ID"),
        BotCommand("bring_ball", "Indicate you're bringing a ball"),  
    ]
    for attempt in range(max_retries):
        try:
            await bot.set_my_commands(commands)
            logger.info("Bot commands set successfully")
            return
        except TimedOut:
            logger.warning(f"Timed out while setting bot commands. Attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)  # Wait 5 seconds before retrying
    logger.error("Failed to set bot commands after maximum retries")

async def main():
    if not check_internet_connection():
        logger.error("Cannot start bot due to no internet connection.")
        return

    logger.info(f"Starting bot with token: {BOT_TOKEN[:5]}...")
    application = None
    try:
        application = ApplicationBuilder().token(BOT_TOKEN).build()

        if not await check_telegram_api(application.bot):
            logger.error("Cannot start bot due to Telegram API issues.")
            return

        # Add your command handlers here
        application.add_handler(CommandHandler("register", register))
        application.add_handler(CommandHandler("remove", remove))
        application.add_handler(CommandHandler("print_list", print_list))
        application.add_handler(CommandHandler("approve", approve))
        application.add_handler(CommandHandler("create_game", create_game))
        application.add_handler(CommandHandler("clear_list", clear_list))
        application.add_handler(CommandHandler("send_reminder", manual_reminder))
        application.add_handler(CommandHandler("get_chat_id", get_chat_id))
        application.add_handler(CommandHandler("bring_ball", bring_ball))

        
        await set_commands_with_retry(application.bot)

        # Set up job queue for reminders if available
        if application.job_queue:
            application.job_queue.run_repeating(send_reminders, interval=7200, first=10)
            logger.info("Job queue set up successfully")
        else:
            logger.warning("Job queue is not available. Reminders will not be sent automatically.")

        logger.info("Bot started successfully")
        await application.initialize()
        await application.start()
        
        # Start polling with error handling
        async def error_handler(update, context):
            logger.error(f"Exception while handling an update: {context.error}")

        application.add_error_handler(error_handler)

        await application.updater.start_polling(allowed_updates=['message'], 
                                                drop_pending_updates=True)
        logger.info("Bot is polling for updates...")
        
        # Instead of using idle(), we'll use an infinite loop
        while True:
            await asyncio.sleep(1)

    except NetworkError as e:
        logger.error(f"Network error occurred: {e}")
    except TimedOut as e:
        logger.error(f"Request timed out: {e}")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
    finally:
        if application:
            try:
                await application.stop()
                await application.shutdown()
                logger.info("Application has been stopped and shut down.")
            except Exception as e:
                logger.error(f"Error during application shutdown: {e}")
if __name__ == '__main__':
    retry_count = 0
    max_retries = 5
    while retry_count < max_retries:
        try:
            asyncio.run(main())
            break
        except KeyboardInterrupt:
            logger.info("Bot stopped manually")
            break
        except Exception as e:
            logger.error(f"Unhandled exception: {e}")
            retry_count += 1
            logger.info(f"Retrying in 10 seconds... (Attempt {retry_count}/{max_retries})")
            # Use a synchronous sleep here since we're outside of an async context
            import time
            time.sleep(10)
    
    if retry_count == max_retries:
        logger.error("Max retries reached. Bot could not be started.")