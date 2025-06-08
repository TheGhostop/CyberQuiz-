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


def generate_compatible_quiz_format(questions_data):
    """
    Convert quiz data to the format expected by the bot.
    Expected format for each question:
    {
        "question": "Question text",
        "options": ["option1", "option2", "option3", "option4"],
        "answer_index": 0,  # Index of correct answer in options array
        "explanation": "Optional explanation"
    }
    """
    formatted_quiz = []

    for q_data in questions_data:
        # Handle different input formats
        if isinstance(q_data, dict):
            question = q_data.get('question', '')

            # Handle multiple possible field names for correct answer
            correct_answer = (q_data.get('correct_answer') or
                            q_data.get('answer') or
                            q_data.get('correct') or
                            q_data.get('right_answer', ''))

            # Handle multiple possible field names for wrong answers
            wrong_answers = (q_data.get('wrong_answers') or
                           q_data.get('incorrect_answers') or
                           q_data.get('options', []))

            # If options already exist, extract correct answer from them
            if 'options' in q_data and isinstance(q_data['options'], list):
                options = q_data['options'][:]
                if 'answer_index' in q_data:
                    # Already in correct format
                    formatted_quiz.append(q_data)
                    continue
                elif correct_answer and correct_answer in options:
                    # Find correct answer in existing options
                    pass
                else:
                    # Use first option as correct if no correct answer specified
                    correct_answer = options[0] if options else ''
                    wrong_answers = options[1:] if len(options) > 1 else []

            explanation = q_data.get('explanation', '')
        else:
            # Handle other formats as needed
            continue

        if not question or not correct_answer:
            continue

        # Create options list with correct answer in random position
        if isinstance(wrong_answers, list):
            all_options = [correct_answer] + wrong_answers[:3]  # Ensure max 4 options
        else:
            all_options = [correct_answer]

        # Remove duplicates while preserving order
        seen = set()
        unique_options = []
        for opt in all_options:
            if opt not in seen:
                seen.add(opt)
                unique_options.append(opt)

        # Ensure we have at least 2 options
        while len(unique_options) < 2:
            unique_options.append(f"Option {len(unique_options) + 1}")

        # Shuffle options and track correct answer position
        random.shuffle(unique_options)
        correct_index = unique_options.index(correct_answer)

        formatted_question = {
            "question": question,
            "options": unique_options,
            "answer_index": correct_index,
            "explanation": explanation
        }

        formatted_quiz.append(formatted_question)

    return formatted_quiz


def convert_existing_quiz_files():
    """Convert existing quiz files to the new format"""
    converted_count = 0

    for quiz_file in QUIZ_DIR.glob("*.json"):
        try:
            # Read existing file
            with open(quiz_file, 'r', encoding='utf-8') as f:
                quiz_data = json.load(f)

            # Check if already in correct format
            is_valid, _ = validate_quiz_format(quiz_data)
            if is_valid:
                continue

            # Convert to new format
            converted_quiz = generate_compatible_quiz_format(quiz_data)

            # Validate converted quiz
            is_valid, message = validate_quiz_format(converted_quiz)
            if not is_valid:
                print(f"❌ Could not convert {quiz_file.name}: {message}")
                continue

            # Create backup
            backup_file = quiz_file.with_suffix('.json.backup')
            quiz_file.rename(backup_file)

            # Save converted file
            with open(quiz_file, 'w', encoding='utf-8') as f:
                json.dump(converted_quiz, f, indent=2, ensure_ascii=False)

            converted_count += 1
            print(f"✅ Converted {quiz_file.name}")

        except Exception as e:
            print(f"❌ Error converting {quiz_file.name}: {str(e)}")

    return converted_count


def save_quiz_for_today(quiz_data, quiz_name="default"):
    """Save quiz in the format expected by the bot"""
    QUIZ_DIR.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = QUIZ_DIR / f"quiz_{today}_{quiz_name}.json"

    # Convert to compatible format
    compatible_quiz = generate_compatible_quiz_format(quiz_data)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(compatible_quiz, f, indent=2, ensure_ascii=False)

    return filename


def load_quizzes():
    """Load today's quiz files"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sorted(QUIZ_DIR.glob(f"quiz_{today}_*.json"))


def validate_quiz_format(quiz_data):
    """Validate that quiz data is in the correct format"""
    required_fields = ['question', 'options', 'answer_index']

    for i, question in enumerate(quiz_data):
        if not isinstance(question, dict):
            return False, f"Question {i+1} is not a dictionary"

        for field in required_fields:
            if field not in question:
                return False, f"Question {i+1} missing required field: {field}"

        if not isinstance(question['options'], list) or len(question['options']) < 2:
            return False, f"Question {i+1} must have at least 2 options"

        answer_idx = question['answer_index']
        if not isinstance(answer_idx, int) or answer_idx < 0 or answer_idx >= len(question['options']):
            return False, f"Question {i+1} has invalid answer_index"

    return True, "Valid format"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome to Cyber Quiz Bot!\n\n"
        "Commands:\n"
        "/join - Join the quiz queue\n"
        "/quiz - Check quiz status\n"
        "/generate - Generate new quiz (admin only)\n\n"
        "Quiz starts when 5 users join!"
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user

    # Check if quiz is already running
    if chat_id in group_states:
        await update.message.reply_text("❌ Quiz is already running! Wait for it to finish.")
        return

    waiting_users.setdefault(chat_id, set()).add(user.id)
    count = len(waiting_users[chat_id])

    await update.message.reply_text(f"✅ {user.first_name} joined! Total: {count}/5")

    if count >= 5:
        await start_quiz(chat_id, context)


async def start_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Start the quiz for a group"""
    quizzes = load_quizzes()
    if not quizzes:
        await context.bot.send_message(chat_id, "❌ No quiz available for today. Use /generate to create one.")
        waiting_users[chat_id].clear()
        return

    # Select a quiz file
    quiz_file = quizzes[hash(chat_id) % len(quizzes)]

    try:
        with open(quiz_file, 'r', encoding='utf-8') as f:
            quiz = json.load(f)

        # Validate quiz format
        is_valid, message = validate_quiz_format(quiz)
        if not is_valid:
            await context.bot.send_message(chat_id, f"❌ Quiz format error: {message}")
            waiting_users[chat_id].clear()
            return

        # Limit to 10 questions and shuffle
        quiz = quiz[:10]
        random.shuffle(quiz)

        # Initialize group state
        group_states[chat_id] = {
            'quiz': quiz,
            'current_q': 0,
            'answered': set(),
            'scores': {},
        }

        # Clear waiting users
        waiting_users[chat_id].clear()

        # Send welcome message
        await context.bot.send_message(
            chat_id,
            f"🎉 Quiz Started!\n📝 {len(quiz)} questions\n⏱️ 15 seconds per question\n\nLet's begin!"
        )

        # Start first question after a short delay
        await asyncio.sleep(2)
        await send_question(chat_id, context)

    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Error loading quiz: {str(e)}")
        waiting_users[chat_id].clear()


async def send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = group_states.get(chat_id)
    if not state:
        return

    idx = state['current_q']
    quiz = state['quiz']

    if idx >= len(quiz):
        await end_quiz(chat_id, context)
        return

    qdata = quiz[idx]
    question_text = f"Q{idx+1}: {qdata['question']}\n\nBy:- @PyCrypt"
    options = qdata['options']
    correct_answer_index = qdata['answer_index']

    try:
        poll_msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_answer_index,  # Use the original correct_answer_index
            is_anonymous=False,
            allows_multiple_answers=False,
            open_period=15,
        )

        # Store poll mapping
        context.bot_data[poll_msg.poll.id] = {
            'chat_id': chat_id,
            'correct_answer': options[correct_answer_index],
            'explanation': qdata.get('explanation', ''),
        }

        state['answered'].clear()

    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Error sending question: {str(e)}")
        await end_quiz(chat_id, context)



async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll answers from users"""
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

    # Mark user as answered for this question
    state['answered'].add(user_id)

    # Update score if answer is correct
    if answer.option_ids and len(answer.option_ids) > 0:
        # User answered, we'll let Telegram handle the scoring through the quiz poll
        pass

async def advance_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Advance to the next question after a delay"""
    await asyncio.sleep(16)  # Wait just slightly longer than poll duration

    state = group_states.get(chat_id)
    if not state:
        return

    state['current_q'] += 1
    await send_question(chat_id, context)



async def end_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """End the quiz and clean up"""
    if chat_id in group_states:
        quiz_length = len(group_states[chat_id]['quiz'])
        del group_states[chat_id]

        await context.bot.send_message(
            chat_id,
            f"🎉 Quiz Completed!\n"
            f"📊 Total Questions: {quiz_length}\n"
            f"Thanks for playing! Use /join to start a new quiz."
        )

    # Clear waiting users
    if chat_id in waiting_users:
        waiting_users[chat_id].clear()


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show quiz status"""
    chat_id = update.effective_chat.id

    if chat_id in group_states:
        state = group_states[chat_id]
        current = state['current_q'] + 1
        total = len(state['quiz'])
        await update.message.reply_text(f"📊 Quiz in progress: Question {current}/{total}")
    elif chat_id in waiting_users and waiting_users[chat_id]:
        count = len(waiting_users[chat_id])
        await update.message.reply_text(f"👥 Waiting for players: {count}/5 joined")
    else:
        await update.message.reply_text("👥 No active quiz. Use /join to start one!")


async def convert_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert existing quiz files to new format"""
    try:
        converted_count = convert_existing_quiz_files()
        if converted_count > 0:
            await update.message.reply_text(f"✅ Converted {converted_count} quiz files to new format!")
        else:
            await update.message.reply_text("ℹ️ No quiz files needed conversion.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error converting quiz files: {str(e)}")


async def generate_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a sample quiz (for demonstration)"""
    # Sample quiz data - replace this with your actual quiz generation logic
    sample_quiz_data = [
        {
            "question": "What does HTML stand for?",
            "correct_answer": "HyperText Markup Language",
            "wrong_answers": ["Home Tool Markup Language", "Hyperlinks Text Mark Language", "Hyperlinking Text Marking Language"],
            "explanation": "HTML stands for HyperText Markup Language, the standard markup language for web pages."
        },
        {
            "question": "Which programming language is known as the 'language of the web'?",
            "correct_answer": "JavaScript",
            "wrong_answers": ["Python", "Java", "C++"],
            "explanation": "JavaScript is often called the 'language of the web' because it runs in web browsers."
        },
        {
            "question": "What does CSS stand for?",
            "correct_answer": "Cascading Style Sheets",
            "wrong_answers": ["Computer Style Sheets", "Creative Style Sheets", "Colorful Style Sheets"],
            "explanation": "CSS stands for Cascading Style Sheets, used for styling web pages."
        }
    ]

    try:
        filename = save_quiz_for_today(sample_quiz_data, "sample")
        await update.message.reply_text(f"✅ Sample quiz generated: {filename.name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error generating quiz: {str(e)}")


# Add a function to handle quiz ending when poll closes
async def handle_poll_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle poll updates (when poll closes)"""
    poll = update.poll
    if not poll or poll.is_closed:
        # Poll closed, advance to next question
        poll_data = context.bot_data.get(poll.id)
        if poll_data:
            chat_id = poll_data['chat_id']
            # Schedule next question
            asyncio.create_task(advance_question(chat_id, context))


if __name__ == '__main__':
    # Ensure quiz directory exists
    QUIZ_DIR.mkdir(exist_ok=True)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('join', join))
    app.add_handler(CommandHandler('quiz', quiz_command))
    app.add_handler(CommandHandler('generate', generate_quiz_command))
    app.add_handler(CommandHandler('convert', convert_quiz_command))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    print("🤖 Quiz Bot starting...")
    app.run_polling()
