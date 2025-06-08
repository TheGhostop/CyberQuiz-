import json
import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path
from telegram import Update, Poll
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
    CallbackContext,
)

BOT_TOKEN = '8157656507:AAETltntAoxF81gtOSnd4BcSyxLexgXzemw'
QUIZ_DIR = Path("daily_quizzes")

waiting_users: dict[int, set[int]] = {}
group_states: dict[int, dict] = {}


def load_quizzes():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sorted(QUIZ_DIR.glob(f"quiz_{today}_*.json"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome to Cyber Quiz Bot! Use /join to participate. Quiz starts when 5 users join."
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    waiting_users.setdefault(chat_id, set()).add(user.id)

    count = len(waiting_users[chat_id])
    await update.message.reply_text(f"✅ {user.first_name} joined! Total: {count}/1")

    if count >= 1:
        quizzes = load_quizzes()
        if not quizzes:
            await update.message.reply_text("❌ No quiz available for today.")
            return

        quiz_file = quizzes[hash(chat_id) % len(quizzes)]
        with open(quiz_file) as f:
            quiz = json.load(f)[:10]

        random.shuffle(quiz)
        group_states[chat_id] = {
            'quiz': quiz,
            'current_q': 0,
            'answered': set(),
        }
        waiting_users[chat_id].clear()
        # start first question
        await send_question(chat_id, context)


async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = group_states.get(chat_id)
    if not state:
        return
    idx = state['current_q']
    quiz = state['quiz']
    if idx >= len(quiz):
        await context.bot.send_message(chat_id, "🎉 Quiz ended! Thanks for playing.")
        return

    qdata = quiz[idx]
    question_text = f"Q{idx+1}: {qdata['question']}\n\nBy:- @PyCrypt"
    options = qdata['options'][:]
    orig_correct = qdata.get('answer_index', 0)

    # Shuffle and track correct
    enumerated = list(enumerate(options))
    random.shuffle(enumerated)
    shuffled_options = [opt for _, opt in enumerated]
    new_correct = next(i for i, (orig_i, _) in enumerate(enumerated) if orig_i == orig_correct)

    poll_msg = await context.bot.send_poll(
        chat_id=chat_id,
        question=question_text,
        options=shuffled_options,
        type=Poll.QUIZ,
        correct_option_id=new_correct,
        is_anonymous=False,
        allows_multiple_answers=False,
    )

    # Store poll mapping
    context.bot_data[poll_msg.poll.id] = {
        'chat_id': chat_id,
    }
    # reset answered for this question
    state['answered'].clear()


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    answer = update.poll_answer
    user_id = answer.user.id
    poll_id = answer.poll_id
    poll_data = context.bot_data.get(poll_id)
    if not poll_data:
        return

    chat_id = poll_data['chat_id']
    state = group_states.get(chat_id)
    if not state or user_id in state['answered']:
        return

    # Mark as answered
    state['answered'].add(user_id)
    # After a delay, advance to next
    await asyncio.sleep(5)
    state['current_q'] += 1
    await send_question(chat_id, context)


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("👥 Quiz starts when 5 users join using /join")


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('join', join))
    app.add_handler(CommandHandler('quiz', quiz_command))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    app.run_polling()
