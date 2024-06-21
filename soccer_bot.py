import logging
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, JobQueue
from datetime import datetime
import pytz
from functools import wraps
import asyncio

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Bot token
TOKEN = '7303862349:AAEdIRwQddZI026xqxt3DjnUW7w_avcQPQg'  

# Lists for players
playing_list = []
waiting_list = []
MAX_PLAYERS = 15
game_created = False

# Dictionary to track approvals
approvals = {}

# Group chat ID
GROUP_CHAT_ID = '-4262387584'  

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
    
    print(f"Register command used by {user_name}")

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
    
    print(f"Remove command used by {user_name}")

@private_chat_only
async def print_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global game_created
    if not game_created:
        await update.message.reply_text("No game has been created yet.")
        return
    message = "Playing List:\n"
    for i, player in enumerate(playing_list, 1):
        message += f"{i}. @{player}\n"
    message += "\nWaiting List:\n"
    for i, player in enumerate(waiting_list, 1):
        message += f"{i}. @{player}\n"
    await update.message.reply_text(message)
    print(f"Print list command used by @{update.effective_user.username}")

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
        await update.message.reply_text(f"Your attendance has been approved, {user.first_name}.")
    else:
        await update.message.reply_text("You're not in the playing list.")
    print(f"Approve command used by {user_name}")

@private_chat_only
async def create_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global playing_list, waiting_list, approvals, game_created
    playing_list = []
    waiting_list = []
    approvals = {}
    game_created = True
    await update.message.reply_text("New game created for Thursday 6:30-8:30 PM. Lists have been reset.")
    print(f"Create game command used by @{update.effective_user.username}")

@private_chat_only
async def clear_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global playing_list, waiting_list, approvals, game_created
    playing_list = []
    waiting_list = []
    approvals = {}
    game_created = False
    await update.message.reply_text("All lists have been cleared. Use /create_game to start a new game.")
    print(f"Clear list command used by @{update.effective_user.username}")
    
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
    
    print(f"Manual reminder command used by @{update.effective_user.username}")
  
async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    if chat_type == 'private':
        await update.message.reply_text(f"This private chat ID is: {chat_id}")
    else:
        await update.message.reply_text(f"This {chat_type} chat ID is: {chat_id}")
    print(f"Get chat ID command used by @{update.effective_user.username} in {chat_type} chat")

async def set_commands(bot):
    commands = [
        BotCommand("register", "Register for the game"),
        BotCommand("remove", "Remove yourself from the game"),
        BotCommand("print_list", "Show the current player lists"),
        BotCommand("approve", "Approve your attendance"),
        BotCommand("create_game", "Create a new game and reset lists"),
        BotCommand("clear_list", "Clear all lists"),
        BotCommand("send_reminder", "Manually send a reminder"),
        BotCommand("get_chat_id", "Get the chat ID"),
    ]
    await bot.set_my_commands(commands)

async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("print_list", print_list))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("create_game", create_game))
    application.add_handler(CommandHandler("clear_list", clear_list))
    application.add_handler(CommandHandler("send_reminder", manual_reminder))
    application.add_handler(CommandHandler("get_chat_id", get_chat_id))
    
    await set_commands(application.bot)

    # Set up job queue for reminders
    job_queue = application.job_queue
    job_queue.run_repeating(send_reminders, interval=7200, first=10)  # Runs every 2 hours

    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
