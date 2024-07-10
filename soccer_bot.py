import logging
import asyncio
import os
import requests
import telegram
from telegram import Update, BotCommand, ChatMemberUpdated, ChatMember
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ChatMemberHandler, filters
from telegram.error import NetworkError, TimedOut
from datetime import datetime
import pytz
from functools import wraps
import random
from typing import Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
GROUP_CHAT_ID = os.environ.get('GROUP_CHAT_ID')

if not BOT_TOKEN or not GROUP_CHAT_ID:
    raise ValueError("BOT_TOKEN and GROUP_CHAT_ID must be set as environment variables")

APPROVE_EMOJI = "✅"
BALL_EMOJI = "⚽"
MAX_PLAYERS = 15

playing_list = []
waiting_list = []
approvals = {}
bringing_ball = set()
game_created = False

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

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = GROUP_CHAT_ID
        logger.info(f"Checking admin status for user {user_id} in chat {chat_id}")
        try:
            user = await context.bot.get_chat_member(chat_id, user_id)
            logger.info(f"User status: {user.status}")
            if user.status not in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                logger.info(f"User {user_id} is not an admin or owner")
                await update.message.reply_text("This command is only available to group administrators.")
                return
            logger.info(f"User {user_id} is an admin or owner, executing command")
            return await func(update, context)
        except Exception as e:
            logger.error(f"Error checking admin status for user {user_id}: {e}")
            await update.message.reply_text("An error occurred while checking your permissions. Please try again later.")
            return
    return wrapper

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
    user_name = user.username or f"{user.first_name}_{user.id}"
    
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
    user_name = user.username or f"{user.first_name}_{user.id}"
    
    if user_name in playing_list:
        playing_list.remove(user_name)
        approvals.pop(user_name, None)
        bringing_ball.discard(user_name)
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
    user_name = user.username or f"{user.first_name}_{user.id}"
    
    if user_name in playing_list:
        approvals[user_name] = True
        await update.message.reply_text(f"Your attendance has been approved, {user.first_name}. {APPROVE_EMOJI}")
    else:
        await update.message.reply_text("You're not in the playing list.")
    logger.info(f"Approve command used by {user_name}")

@admin_only
async def create_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global playing_list, waiting_list, approvals, bringing_ball, game_created
    if game_created:
        await update.message.reply_text("A game has already been created. Use /clear_list to reset everything before creating a new game.")
        return
    playing_list = []
    waiting_list = []
    approvals = {}
    bringing_ball = set()
    game_created = True
    
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text="New game created for Wednesday 21:00-23:00 PM. Use /register in private to join the game!"
    )
    
    await update.message.reply_text("New game created and announced in the group chat.")
    logger.info(f"Create game command used by @{update.effective_user.username}")

@admin_only
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
    user_name = user.username or f"{user.first_name}_{user.id}"
    
    if user_name in playing_list:
        if user_name in bringing_ball:
            bringing_ball.remove(user_name)
            await update.message.reply_text(f"{user.first_name}, we've noted that you're no longer bringing a ball.")
        else:
            bringing_ball.add(user_name)
            await update.message.reply_text(f"Great, {user.first_name}! We've noted that you're bringing a ball. {BALL_EMOJI}")
    else:
        await update.message.reply_text("You're not in the playing list. Please register for the game first.")
    logger.info(f"Bring ball command used by {user_name}")

@admin_only
async def register_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide a username to register.")
        return
    
    username = context.args[0].lstrip('@')
    if username in playing_list or username in waiting_list:
        await update.message.reply_text(f"@{username} is already registered.")
    elif len(playing_list) < MAX_PLAYERS:
        playing_list.append(username)
        await update.message.reply_text(f"@{username} has been added to the playing list.")
    else:
        waiting_list.append(username)
        await update.message.reply_text(f"@{username} has been added to the waiting list.")
    
    logger.info(f"Register player command used for @{username}")

@admin_only
async def remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Please provide a username to remove.")
        return
    
    username = context.args[0].lstrip('@')
    if username in playing_list:
        playing_list.remove(username)
        approvals.pop(username, None)
        bringing_ball.discard(username)
        await update.message.reply_text(f"@{username} has been removed from the playing list.")
        if waiting_list:
            moved_player = waiting_list.pop(0)
            playing_list.append(moved_player)
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID, 
                text=f"@{moved_player} has been moved from the waiting list to the playing list."
            )
    elif username in waiting_list:
        waiting_list.remove(username)
        await update.message.reply_text(f"@{username} has been removed from the waiting list.")
    else:
        await update.message.reply_text(f"@{username} is not registered for the game.")
    
    logger.info(f"Remove player command used for @{username}")

async def send_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(pytz.timezone('Asia/Jerusalem'))
    if now.weekday() == 2 and now.hour >= 10 and now.hour < 17:
        unapproved = [player for player in playing_list if player not in approvals]
        if unapproved:
            message = "Reminder: Please approve your attendance before 4 PM. Use the /approve command in a private chat with me.\n\n"
            for player in unapproved:
                message += f"@{player}\n"
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message)

@admin_only
async def divide_teams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(playing_list) < 9:
        await update.message.reply_text("Not enough players to divide into teams. At least 9 players are needed.")
        return
    
    random.shuffle(playing_list)
    team_size = len(playing_list) // 3
    team1 = playing_list[:team_size]
    team2 = playing_list[team_size:2*team_size]
    team3 = playing_list[2*team_size:]
    
    message = "Teams have been divided as follows:\n\n"
    message += "Team 1 (Starts playing):\n" + "\n".join(f"@{player}" for player in team1) + "\n\n"
    message += "Team 2 (Starts playing):\n" + "\n".join(f"@{player}" for player in team2) + "\n\n"
    message += "Team 3 (Starts on the bench):\n" + "\n".join(f"@{player}" for player in team3) + "\n\n"
    message += "Team 3 will start on the bench and rotate in. Good luck and have fun!"
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message)
    logger.info(f"Divide teams command used by @{update.effective_user.username}")

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
        
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=message)
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
        BotCommand("register_player", "Admin: Register another player"),
        BotCommand("remove_player", "Admin: Remove another player"),
        BotCommand("divide_teams", "Admin: Divide players into teams"),
    ]
    for attempt in range(max_retries):
        try:
            await bot.set_my_commands(commands)
            logger.info("Bot commands set successfully")
            return
        except TimedOut:
            logger.warning(f"Timed out while setting bot commands. Attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    logger.error("Failed to set bot commands after maximum retries")

async def send_welcome_message(update: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = extract_status_change(update.chat_member)
    if result is None:
        return

    was_member, is_member = result

    if not was_member and is_member:
        user = update.chat_member.new_chat_member.user
        welcome_message = (
            f"Welcome to the football group, {user.first_name}! 🎉⚽\n\n"
            "Here are the rules and how to use the bot:\n\n"
            "1. Games are typically on Wedneday, 21:00-23:00 PM.\n"
            "2. Use /register in a private chat with me to join a game.\n"
            "3. Use /approve to confirm your attendance before 6 PM on game day.\n"
            "4. Use /remove if you can't make it to a game you've registered for.\n"
            "5. Use /bring_ball if you can bring a ball to the game.\n"
            "6. Check /print_list to see who's playing and on the waiting list.\n\n"
            "Enjoy the games and have fun! If you have any questions, feel free to ask in the group."
        )
        try:
            await context.bot.send_message(chat_id=user.id, text=welcome_message)
            logger.info(f"Welcome message sent to new member @{user.username or user.first_name}")
        except Exception as e:
            logger.error(f"Failed to send welcome message to @{user.username or user.first_name}: {e}")
            await update.effective_chat.send_message(
                f"Welcome {user.mention_html()}!\n\n"
                "I tried to send you a private message with some information, "
                "but I couldn't. Please start a private chat with me and send /start for more information.",
                parse_mode='HTML'
            )

def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[Tuple[bool, bool]]:
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = (
        old_status
        in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ]
        or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    )
    is_member = (
        new_status
        in [
            ChatMember.MEMBER,
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
        ]
        or (new_status == ChatMember.RESTRICTED and new_is_member is True)
    )

    return was_member, is_member

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

        application.add_handler(CommandHandler("register", register))
        application.add_handler(CommandHandler("remove", remove))
        application.add_handler(CommandHandler("print_list", print_list))
        application.add_handler(CommandHandler("approve", approve))
        application.add_handler(CommandHandler("create_game", create_game))
        application.add_handler(CommandHandler("clear_list", clear_list))
        application.add_handler(CommandHandler("send_reminder", manual_reminder))
        application.add_handler(CommandHandler("get_chat_id", get_chat_id))
        application.add_handler(CommandHandler("bring_ball", bring_ball))
        application.add_handler(CommandHandler("register_player", register_player))
        application.add_handler(CommandHandler("remove_player", remove_player))
        application.add_handler(CommandHandler("divide_teams", divide_teams))
        application.add_handler(ChatMemberHandler(send_welcome_message, ChatMemberHandler.CHAT_MEMBER))

        await set_commands_with_retry(application.bot)

        if application.job_queue:
            application.job_queue.run_repeating(send_reminders, interval=7200, first=10)
            logger.info("Job queue set up successfully")
        else:
            logger.warning("Job queue is not available. Reminders will not be sent automatically.")

        logger.info("Bot started successfully")
        await application.initialize()
        await application.start()
        
        async def error_handler(update, context):
            logger.error(f"Exception while handling an update: {context.error}")

        application.add_error_handler(error_handler)

        await application.updater.start_polling(allowed_updates=['message', 'chat_member'], 
                                                drop_pending_updates=True)
        logger.info("Bot is polling for updates...")
        
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
            import time
            time.sleep(10)
    
    if retry_count == max_retries:
        logger.error("Max retries reached. Bot could not be started.")