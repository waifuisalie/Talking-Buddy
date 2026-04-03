import sys
sys.path.insert(0, '/home/pi/Talking-Buddy/rpi5-chatbot/src')
from voice_chatbot import SentenceDetector
import inspect
print(inspect.getfile(SentenceDetector))
