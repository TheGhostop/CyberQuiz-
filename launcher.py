import multiprocessing
import os

def start_bot():
    os.system("python bot.py")

def start_web():
    os.system("python app.py")

if __name__ == "__main__":
    multiprocessing.Process(target=start_bot).start()
    multiprocessing.Process(target=start_web).start()
