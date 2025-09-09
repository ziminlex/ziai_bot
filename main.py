import sqlite3
import json
from datetime import datetime
import os
import logging
import requests
import asyncio
import time
import re
import random
import signal
import sys
import aiohttp
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler, CallbackContext
from telegram.error import Conflict
from enum import Enum
from collections import deque, defaultdict
import numpy as np
import humanize
from dateutil import parser
import uuid
from typing import Dict, Any, List, Optional
import hashlib
import json

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Обработчик сигналов для graceful shutdown
def signal_handler(sig, frame):
    print("\n🛑 Останавливаю бота...")
    # Создаем задачу для graceful shutdown
    if 'application' in globals() and application.running:
        application.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Ваши ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

# Настройки почты
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.yandex.ru")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER", "ziminleks@yandex.ru")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO", "ziminleks@yandex.ru")

# URL API Yandex GPT
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Контекст беседы для каждого пользователя
conversation_context = {}

class DeepContextAnalyzer:
    """Глубокий анализ контекста беседы"""
    
    def __init__(self):
        self.topic_memory = defaultdict(lambda: {'count': 0, 'last_mentioned': None, 'sentiment': 0.5})
        self.conversation_flow = deque(maxlen=10)
        
    def extract_deep_context(self, message, history, user_context):
        """Извлечение глубокого контекста из всей беседы"""
        context = {
            'current_topics': self._extract_topics(message),
            'historical_topics': self._analyze_historical_topics(history),
            'emotional_arc': self._analyze_emotional_arc(history),
            'conversation_rhythm': self._analyze_conversation_rhythm(history),
            'unfinished_threads': self._find_unfinished_threads(history),
            'user_patterns': self._analyze_user_patterns(history, user_context)
        }
        return context
    
    def _extract_topics(self, text):
        """Извлечение тем с весами"""
        words = re.findall(r'\b[а-яё]{3,}\b', text.lower())
        stop_words = {'этот', 'очень', 'который', 'когда', 'потом', 'тогда', 'вообще', 'значит'}
        topics = {}
        
        for word in set(words) - stop_words:
            if len(word) > 2:
                # Вес based on частоте и позиции
                weight = words.count(word) * 0.3
                if word in text[:50]:  # Упоминание в начале
                    weight += 0.2
                topics[word] = min(1.0, weight)
        
        return dict(sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5])
    
    def _analyze_historical_topics(self, history):
        """Анализ исторических тем"""
        historical_topics = {}
        for i, msg in enumerate(history[-20:]):  # Последние 20 сообщений
            if 'user' in msg:
                topics = self._extract_topics(msg['user'])
                for topic, weight in topics.items():
                    if topic in historical_topics:
                        historical_topics[topic] += weight * (0.9 ** i)  # Экспоненциальное затухание
                    else:
                        historical_topics[topic] = weight * (0.9 ** i)
        
        return dict(sorted(historical_topics.items(), key=lambda x: x[1], reverse=True)[:8])
    
    def _analyze_emotional_arc(self, history):
        """Анализ эмоциональной дуги беседы"""
        emotions = []
        for msg in history[-10:]:
            if 'user' in msg:
                emotional_score = self._calculate_emotional_score(msg['user'])
                emotions.append(emotional_score)
        
        if len(emotions) > 2:
            trend = np.polyfit(range(len(emotions)), emotions, 1)[0]
            return {
                'current_mood': emotions[-1] if emotions else 0.5,
                'trend': trend,
                'volatility': np.std(emotions) if len(emotions) > 1 else 0
            }
        return {'current_mood': 0.5, 'trend': 0, 'volatility': 0}
    
    def _calculate_emotional_score(self, text):
        """Вычисление эмоционального скора"""
        positive = sum(1 for word in ['рад', 'счастлив', 'хорошо', 'отлично', 'люблю'] if word in text.lower())
        negative = sum(1 for word in ['грустно', 'плохо', 'ненавижу', 'злой', 'обидно'] if word in text.lower())
        
        total = positive + negative
        if total == 0:
            return 0.5
        return positive / total
    
    def _analyze_conversation_rhythm(self, history):
        """Анализ ритма беседы"""
        if len(history) < 3:
            return {'pace': 'medium', 'initiative': 0.5}
        
        # Анализ темпа
        response_times = []
        for i in range(1, min(10, len(history))):
            if 'timestamp' in history[i] and 'timestamp' in history[i-1]:
                delta = (history[i]['timestamp'] - history[i-1]['timestamp']).total_seconds()
                response_times.append(delta)
        
        avg_response = np.mean(response_times) if response_times else 60
        if avg_response < 30:
            pace = 'fast'
        elif avg_response < 120:
            pace = 'medium'
        else:
            pace = 'slow'
        
        # Анализ инициативы
        user_messages = sum(1 for msg in history[-10:] if 'user' in msg)
        initiative = user_messages / min(10, len(history))
        
        return {'pace': pace, 'initiative': initiative}
    
    def _find_unfinished_threads(self, history):
        """Поиск незавершенных тем"""
        unfinished = []
        questions = []
        
        for msg in history[-10:]:
            if 'user' in msg and '?' in msg['user']:
                questions.append(msg['user'])
            if 'bot' in msg and '?' in msg['bot']:
                # Проверяем, был ли ответ на вопрос бота
                next_msgs = history[history.index(msg)+1:]
                if not any('user' in m and '?' not in m.get('user', '') for m in next_msgs[:2]):
                    unfinished.append(msg['bot'])
        
        return {'user_questions': questions[-3:], 'bot_questions': unfinished}
    
    def _analyze_user_patterns(self, history, user_context):
        """Анализ паттернов пользователя"""
        patterns = {
            'question_frequency': 0,
            'emotional_consistency': 0,
            'topic_persistence': 0,
            'response_style': 'balanced'
        }
        
        if len(history) < 5:
            return patterns
        
        # Частота вопросов
        questions = sum(1 for msg in history[-10:] if 'user' in msg and '?' in msg['user'])
        patterns['question_frequency'] = questions / min(10, len(history))
        
        # Стиль ответов
        message_lengths = [len(msg.get('user', '')) for msg in history[-10:] if 'user' in msg]
        if message_lengths:
            avg_length = np.mean(message_lengths)
            patterns['response_style'] = 'detailed' if avg_length > 50 else 'concise'
        
        return patterns

class HumanConversationSimulator:
    """Симулятор человеческой беседы"""
    
    def __init__(self):
        self.typing_profiles = self._create_typing_profiles()
        self.conversation_styles = self._create_conversation_styles()
        self.memory_system = MemorySystem()
        
    def _create_typing_profiles(self):
        """Профили печатания для разных типов личности"""
        return {
            'fast': {'base_speed': 0.02, 'variation': 0.7, 'error_rate': 0.005},
            'normal': {'base_speed': 0.03, 'variation': 0.8, 'error_rate': 0.01},
            'thoughtful': {'base_speed': 0.04, 'variation': 0.9, 'error_rate': 0.015},
            'emotional': {'base_speed': 0.025, 'variation': 1.2, 'error_rate': 0.02}
        }
    
    def _create_conversation_styles(self):
        """Стили ведения беседы"""
        return {
            'active': {'question_rate': 0.4, 'topic_change': 0.3, 'detail_level': 0.8},
            'reactive': {'question_rate': 0.2, 'topic_change': 0.1, 'detail_level': 0.6},
            'balanced': {'question_rate': 0.3, 'topic_change': 0.2, 'detail_level': 0.7},
            'deep': {'question_rate': 0.25, 'topic_change': 0.15, 'detail_level': 0.9}
        }
    
    async def simulate_human_response(self, message, context, history):
        """Симуляция человеческого ответа"""
        # Анализ контекста
        deep_context = context['deep_context']
        
        # Выбор стиля based on контекста
        conversation_style = self._select_conversation_style(deep_context)
        typing_profile = self._select_typing_profile(deep_context)
        
        # Время на обдумывание
        thinking_time = self._calculate_thinking_time(message, deep_context, history)
        if thinking_time > 0.5:
            await asyncio.sleep(thinking_time)
        
        # Имитация печатания
        typing_time = self._calculate_typing_time(message, typing_profile, context)
        await asyncio.sleep(typing_time)
        
        return {
            'thinking_time': thinking_time,
            'typing_time': typing_time,
            'conversation_style': conversation_style,
            'typing_profile': typing_profile
        }
    
    def _select_conversation_style(self, deep_context):
        """Выбор стиля беседы based on контекста"""
        mood = deep_context['emotional_arc']['current_mood']
        pace = deep_context['conversation_rhythm']['pace']
        
        if mood > 0.7 and pace == 'fast':
            return 'active'
        elif mood < 0.3:
            return 'reactive'
        elif deep_context['user_patterns']['response_style'] == 'detailed':
            return 'deep'
        else:
            return 'balanced'
    
    def _select_typing_profile(self, deep_context):
        """Выбор профиля печатания"""
        volatility = deep_context['emotional_arc']['volatility']
        if volatility > 0.3:
            return 'emotional'
        elif deep_context['conversation_rhythm']['pace'] == 'fast':
            return 'fast'
        else:
            return random.choice(['normal', 'thoughtful'])
    
    def _calculate_thinking_time(self, message, deep_context, history):
        """Время на обдумывание"""
        base_time = random.uniform(0.5, 2.0)
        
        # Множители сложности
        complexity = 1.0
        if '?' in message:
            complexity += 0.5
        if len(message) > 100:
            complexity += 0.3
        if deep_context['emotional_arc']['volatility'] > 0.2:
            complexity += 0.4
        
        # Учет истории
        if len(history) > 5:
            recent_emotional = [m for m in history[-3:] if 'emotional_score' in m]
            if recent_emotional and any(m['emotional_score'] < 0.3 for m in recent_emotional):
                complexity += 0.5
        
        return base_time * complexity
    
    def _calculate_typing_time(self, message, profile, context):
        """Время печатания"""
        profile_config = self.typing_profiles[profile]
        base_time = len(message) * profile_config['base_speed']
        
        # Вариативность
        variation = random.uniform(1 - profile_config['variation'], 
                                 1 + profile_config['variation'])
        
        # Опыт общения (со временем печатает быстрее)
        experience = max(0.7, 1.0 - (context.get('messages_count', 0) * 0.0005))
        
        return base_time * variation * experience

class MemorySystem:
    """Система памяти и воспоминаний"""
    
    def __init__(self):
        self.long_term_memory = {}
        self.associative_triggers = self._create_associative_triggers()
    
    def _create_associative_triggers(self):
        """Ассоциативные триггеры для воспоминаний"""
        return {
            'time_based': {
                'today': "Кстати, помнишь сегодня мы говорили о {}?",
                'recent': "Вспомнил наш недавний разговор про {}",
                'past': "О, давно мы не вспоминали о {}"
            },
            'topic_based': {
                'strong': "Говоря о {}, не могу не вспомнить...",
                'medium': "Это напоминает мне о {}",
                'weak': "Кстати, о {}..."
            },
            'emotional': {
                'positive': "Вспомнилось как мы весело обсуждали {}",
                'negative': "Помнишь тот сложный разговор о {}?",
                'neutral': "Пришло на ум наше обсуждение {}"
            }
        }
    
    def create_contextual_memory(self, current_message, history, user_context):
        """Создание контекстных воспоминаний"""
        if len(history) < 3:
            return None
        
        current_topics = set(DeepContextAnalyzer()._extract_topics(current_message).keys())
        memory_candidates = []
        
        # Поиск в истории по темам
        for i, past_msg in enumerate(history[-20:]):
            if 'user' in past_msg:
                past_topics = set(DeepContextAnalyzer()._extract_topics(past_msg['user']).keys())
                common_topics = current_topics.intersection(past_topics)
                
                if common_topics:
                    days_ago = (datetime.now() - past_msg.get('timestamp', datetime.now())).days
                    memory_candidates.append({
                        'topics': common_topics,
                        'recency': days_ago,
                        'message': past_msg['user'],
                        'index': i
                    })
        
        if not memory_candidates:
            return None
        
        # Выбор наиболее релевантного воспоминания
        best_memory = max(memory_candidates, key=lambda x: (
            len(x['topics']) * 0.5 + 
            (1 / (x['recency'] + 1)) * 0.3 +
            random.random() * 0.2
        ))
        
        topic = random.choice(list(best_memory['topics']))
        return self._format_memory_reference(topic, best_memory['recency'])
    
    def _format_memory_reference(self, topic, days_ago):
        """Форматирование ссылки на воспоминание"""
        if days_ago == 0:
            time_key = 'today'
        elif days_ago <= 3:
            time_key = 'recent'
        else:
            time_key = 'past'
        
        # Случайный выбор типа ссылки
        memory_type = random.choice(['time_based', 'topic_based', 'emotional'])
        intensity = random.choice(['strong', 'medium', 'weak'])
        
        template = self.associative_triggers[memory_type].get(
            intensity, 
            self.associative_triggers[memory_type]['medium']
        )
        
        return template.format(topic)

class EmotionalIntelligence:
    """Эмоциональный интеллект"""
    
    def __init__(self):
        self.emotional_models = self._create_emotional_models()
        self.empathy_responses = self._create_empathy_responses()
    
    def analyze_emotional_state(self, message, history):
        """Анализ эмоционального состояния"""
        text = message.lower()
        
        # Базовый эмоциональный анализ
        emotions = {
            'joy': self._detect_emotion(text, ['рад', 'счастлив', 'ура', 'класс', 'супер']),
            'sadness': self._detect_emotion(text, ['грустно', 'печально', 'плохо', 'тяжело']),
            'anger': self._detect_emotion(text, ['злой', 'сердит', 'бесит', 'ненавижу']),
            'excitement': self._detect_emotion(text, ['!', '!!', '!!!', 'вау', 'ого']),
            'confusion': self._detect_emotion(text, ['?', '??', '???', 'не понимаю', 'запутался'])
        }
        
        # Анализ эмоциональной дуги
        emotional_trend = self._analyze_emotional_trend(history)
        
        return {
            'current_emotions': emotions,
            'dominant_emotion': max(emotions.items(), key=lambda x: x[1])[0],
            'emotional_trend': emotional_trend,
            'intensity': max(emotions.values()) if emotions else 0
        }
    
    def _detect_emotion(self, text, triggers):
        """Обнаружение эмоции"""
        score = 0
        for trigger in triggers:
            if trigger in text:
                score += 1
        return min(1.0, score * 0.3)
    
    def _analyze_emotional_trend(self, history):
        """Анализ эмоционального тренда"""
        if len(history) < 3:
            return 'stable'
        
        recent_scores = []
        for msg in history[-5:]:
            if 'user' in msg:
                score = self._calculate_emotional_score(msg['user'])
                recent_scores.append(score)
        
        if len(recent_scores) > 2:
            trend = np.polyfit(range(len(recent_scores)), recent_scores, 1)[0]
            if abs(trend) > 0.1:
                return 'improving' if trend > 0 else 'worsening'
        return 'stable'
    
    def _calculate_emotional_score(self, text):
        """Вычисление эмоционального скора"""
        positive = sum(1 for word in ['рад', 'счастлив', 'хорошо', 'отлично'] if word in text.lower())
        negative = sum(1 for word in ['грустно', 'плохо', 'ненавижу', 'злой'] if word in text.lower())
        
        total = positive + negative + 0.001  # избегаем деления на ноль
        return positive / total
    
    def generate_empathic_response(self, emotional_state, response):
        """Генерация эмпатичного ответа"""
        dominant = emotional_state['dominant_emotion']
        intensity = emotional_state['intensity']
        
        if intensity > 0.3:
            # Добавляем эмоциональную реакцию
            emotional_reaction = self._get_emotional_reaction(dominant, intensity)
            if random.random() < 0.6:
                response = f"{emotional_reaction} {response}"
            
            # Добавляем эмпатичную фразу
            if random.random() < 0.4:
                empathic_phrase = self._get_empathic_phrase(dominant, intensity)
                response = f"{response} {empathic_phrase}"
        
        return response
    
    def _get_emotional_reaction(self, emotion, intensity):
        """Получение эмоциональной реакции"""
        reactions = {
            'joy': ['😊', '🎉', '✨', '🥳'],
            'sadness': ['😔', '🤗', '❤️', '💔'],
            'anger': ['😠', '😤', '💢', '⚡'],
            'excitement': ['😃', '🚀', '🌟', '🔥'],
            'confusion': ['🤔', '😕', '🧐', '💭']
        }
        return random.choice(reactions.get(emotion, ['🙂']))
    
    def _get_empathic_phrase(self, emotion, intensity):
        """Получение эмпатичной фразы"""
        phrases = {
            'joy': ['Я рад за тебя!', 'Это прекрасно!', 'Как здорово!'],
            'sadness': ['Понимаю тебя...', 'Мне жаль...', 'Держись!'],
            'anger': ['Понимаю твои чувства', 'Это действительно неприятно'],
            'excitement': ['Здорово!', 'Восхитительно!', 'Я разделяю твой восторг!'],
            'confusion': ['Понимаю твоё замешательство', 'Давай разберемся вместе']
        }
        return random.choice(phrases.get(emotion, ['Понимаю...']))

# Глобальные экземпляры
context_analyzer = DeepContextAnalyzer()
conversation_simulator = HumanConversationSimulator()
memory_system = MemorySystem()
emotional_intelligence = EmotionalIntelligence()

def get_user_context(user_id: int) -> Dict[str, Any]:
    """Получение контекста пользователя из базы данных"""
    try:
        conn = sqlite3.connect("bot_users.db")
        cursor = conn.cursor()
        
        # Получаем базовую информацию о пользователе
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        
        # Получаем историю сообщений
        cursor.execute("""
            SELECT message_text, bot_response, timestamp, emotional_score, topic_tags 
            FROM messages 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 20
        """, (user_id,))
        messages = cursor.fetchall()
        
        # Получаем контекст беседы
        cursor.execute("SELECT * FROM conversation_context WHERE user_id = ?", (user_id,))
        context_data = cursor.fetchone()
        
        conn.close()
        
        # Формируем контекст
        context = {
            'user_id': user_id,
            'history': [],
            'messages_count': 0,
            'last_interaction': None
        }
        
        if user_data:
            context['messages_count'] = user_data[6] if len(user_data) > 6 else 0
            context['last_interaction'] = user_data[5] if len(user_data) > 5 else None
        
        # Добавляем историю сообщений
        for msg in messages:
            context['history'].append({
                'user': msg[0],
                'bot': msg[1],
                'timestamp': datetime.fromisoformat(msg[2]) if isinstance(msg[2], str) else msg[2],
                'emotional_score': msg[3],
                'topics': json.loads(msg[4]) if msg[4] else []
            })
        
        # Добавляем данные контекста
        if context_data:
            try:
                context['deep_context'] = {
                    'current_topics': json.loads(context_data[1]) if context_data[1] else {},
                    'historical_topics': json.loads(context_data[2]) if context_data[2] else {},
                    'emotional_arc': json.loads(context_data[3]) if context_data[3] else {},
                    'conversation_rhythm': json.loads(context_data[4]) if context_data[4] else {},
                    'user_patterns': json.loads(context_data[5]) if context_data[5] else {},
                    'unfinished_threads': json.loads(context_data[6]) if context_data[6] else {}
                }
            except json.JSONDecodeError:
                context['deep_context'] = {}
        
        return context
        
    except Exception as e:
        logger.error(f"Ошибка получения контекста пользователя {user_id}: {e}")
        return {'user_id': user_id, 'history': [], 'messages_count': 0}

def save_complete_context(user_id: int, user_message: str, bot_response: str, 
                         deep_context: Dict[str, Any], emotional_state: Dict[str, Any],
                         response_metrics: Dict[str, Any], memory_reference: Optional[str] = None):
    """Сохранение полного контекста беседы"""
    try:
        conn = sqlite3.connect("bot_users.db")
        cursor = conn.cursor()
        
        # Создаем хэш контекста для уникальности
        context_hash = hashlib.md5(
            f"{user_id}{user_message}{datetime.now().timestamp()}".encode()
        ).hexdigest()
        
        # Извлекаем темы из сообщения
        topics = list(deep_context.get('current_topics', {}).keys())[:5]
        
        # Обновляем или создаем пользователя
        cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, created_at, last_interaction) 
            VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (user_id,))
        
        cursor.execute("""
            UPDATE users SET last_interaction = CURRENT_TIMESTAMP WHERE user_id = ?
        """, (user_id,))
        
        # Сохраняем сообщение
        cursor.execute("""
            INSERT INTO messages 
            (user_id, message_text, bot_response, message_type, emotions, style, 
             typing_time, thinking_time, context_hash, emotional_score, topic_tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, 
            user_message, 
            bot_response,
            'text',
            json.dumps(emotional_state),
            response_metrics.get('conversation_style', 'balanced'),
            response_metrics.get('typing_time', 0),
            response_metrics.get('thinking_time', 0),
            context_hash,
            emotional_state.get('intensity', 0.5),
            json.dumps(topics)
        ))
        
        # Сохраняем контекст беседы
        cursor.execute("""
            INSERT OR REPLACE INTO conversation_context 
            (user_id, current_topics, historical_topics, emotional_arc, 
             conversation_rhythm, user_patterns, unfinished_threads, last_deep_analysis)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            json.dumps(deep_context.get('current_topics', {})),
            json.dumps(deep_context.get('historical_topics', {})),
            json.dumps(deep_context.get('emotional_arc', {})),
            json.dumps(deep_context.get('conversation_rhythm', {})),
            json.dumps(deep_context.get('user_patterns', {})),
            json.dumps(deep_context.get('unfinished_threads', {}))
        ))
        
        # Сохраняем воспоминание, если есть
        if memory_reference:
            cursor.execute("""
                INSERT INTO conversation_memory 
                (user_id, memory_type, content, emotional_weight)
                VALUES (?, 'associative', ?, ?)
            """, (user_id, memory_reference, emotional_state.get('intensity', 0.5)))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка сохранения контекста для пользователя {user_id}: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    welcome_text = f"""
👋 Привет, {user.first_name}!

Я бот с глубоким контекстным анализом. Я запоминаю наши разговоры и стараюсь вести беседу как живой человек.

Что умею:
• Запоминать темы наших разговоров
• Анализировать контекст беседы
• Проявлять эмпатию и понимание
• Вести естественную человеческую беседу

Просто напиши мне что-нибудь, и мы начнем общаться!

Также доступны команды:
/context - показать текущий контекст
/memory - показать память о беседах
"""
    await update.message.reply_text(welcome_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке сообщения: {context.error}")
    
    if update and update.message:
        try:
            await update.message.reply_text(
                "⚠️ Произошла ошибка при обработке сообщения. Попробуйте еще раз позже."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

class UserDatabase:
    def __init__(self, db_name="bot_users.db"):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных с расширенной схемой"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                gender TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_interaction DATETIME,
                conversation_style TEXT DEFAULT 'balanced',
                emotional_profile TEXT
            )
        ''')
        
        # Таблица сообщений с расширенными полями
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_text TEXT,
                bot_response TEXT,
                message_type TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                emotions TEXT,
                style TEXT,
                typing_time REAL,
                thinking_time REAL,
                context_hash TEXT,
                emotional_score REAL,
                topic_tags TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица контекста
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_context (
                user_id INTEGER PRIMARY KEY,
                current_topics TEXT,
                historical_topics TEXT,
                emotional_arc TEXT,
                conversation_rhythm TEXT,
                user_patterns TEXT,
                unfinished_threads TEXT,
                last_deep_analysis DATETIME,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица памяти
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                memory_type TEXT,
                content TEXT,
                emotional_weight REAL,
                last_recalled DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
    
    def get_user(self, user_id: int) -> Optional[tuple]:
        """Получение пользователя по ID"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            conn.close()
            return user
        except Exception as e:
            logger.error(f"Ошибка получения пользователя {user_id}: {e}")
            return None
    
    def create_user(self, user_id: int, username: str = None, 
                   first_name: str = None, last_name: str = None):
        """Создание нового пользователя"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_interaction = CURRENT_TIMESTAMP
            """, (user_id, username, first_name, last_name))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка создания пользователя {user_id}: {e}")
    
    def update_user_interaction(self, user_id: int):
        """Обновление времени последнего взаимодействия"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_interaction = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка обновления взаимодействия пользователя {user_id}: {e}")
    
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики пользователя"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Количество сообщений
            cursor.execute("SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,))
            message_count = cursor.fetchone()[0]
            
            # Последняя активность
            cursor.execute("SELECT last_interaction FROM users WHERE user_id = ?", (user_id,))
            last_interaction = cursor.fetchone()[0]
            
            # Популярные темы
            cursor.execute("""
                SELECT topic_tags, COUNT(*) as count 
                FROM messages 
                WHERE user_id = ? AND topic_tags IS NOT NULL
                GROUP BY topic_tags 
                ORDER BY count DESC 
                LIMIT 5
            """, (user_id,))
            popular_topics = cursor.fetchall()
            
            conn.close()
            
            return {
                'message_count': message_count,
                'last_interaction': last_interaction,
                'popular_topics': popular_topics
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
            return {}

async def process_message_with_deep_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения с глубоким контекстным анализом"""
    try:
        user_id = update.effective_user.id
        user_message = update.message.text
        
        # Получаем расширенный контекст
        user_context = get_user_context(user_id)
        history = user_context.get('history', [])
        
        # Глубокий анализ контекста
        deep_context = context_analyzer.extract_deep_context(user_message, history, user_context)
        
        # Анализ эмоционального состояния
        emotional_state = emotional_intelligence.analyze_emotional_state(user_message, history)
        
        # Поиск воспоминаний
        memory_reference = memory_system.create_contextual_memory(user_message, history, user_context)
        
        # Симуляция человеческого ответа
        response_metrics = await conversation_simulator.simulate_human_response(
            user_message, user_context, history
        )
        
        # Создание промпта с глубоким контекстом
        prompt = create_deep_context_prompt(user_message, deep_context, emotional_state, memory_reference, user_context)
        
        # Генерация ответа
        bot_response = await generate_ai_response(prompt, response_metrics['conversation_style'])
        
        # Добавление эмпатии и человеческих элементов
        bot_response = emotional_intelligence.generate_empathic_response(emotional_state, bot_response)
        if memory_reference and random.random() < 0.6:
            bot_response = f"{memory_reference} {bot_response}"
        
        # Сохранение всего контекста
        save_complete_context(user_id, user_message, bot_response, deep_context, 
                            emotional_state, response_metrics, memory_reference)
        
        # Отправка ответа
        await update.message.reply_text(bot_response)
        
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text("Что-то я запуталась... Давай попробуем еще раз?")

def create_deep_context_prompt(message, deep_context, emotional_state, memory_reference, user_context):
    """Создание промпта с глубоким контекстом"""
    prompt = f"""
Ты - опытный собеседник, который ведет естественную человеческую беседу.

ТЕКУЩИЙ КОНТЕКСТ:
- Сообщение: {message}
- Эмоциональное состояние: {emotional_state['dominant_emotion']} (интенсивность: {emotional_state['intensity']:.2f})
- Настроение: {emotional_state['emotional_trend']}
- Темп беседы: {deep_context['conversation_rhythm']['pace']}

ИСТОРИЯ БЕСЕДЫ:
Текущие темы: {', '.join(list(deep_context['current_topics'].keys())[:3])}
Исторические темы: {', '.join(list(deep_context['historical_topics'].keys())[:3])}
Незавершенные вопросы: {len(deep_context['unfinished_threads']['user_questions'])}

ПАТТЕРНЫ ПОЛЬЗОВАТЕЛЯ:
Стиль ответов: {deep_context['user_patterns']['response_style']}
Частота вопросов: {deep_context['user_patterns']['question_frequency']:.2f}

{'ВОСПОМИНАНИЕ: ' + memory_reference if memory_reference else ''}

ВЕДИ СЕБЯ КАК ЖИВОЙ ЧЕЛОВЕК:
- Учитывай весь контекст беседы
- Проявляй эмпатию к эмоциональному состоянию
- Используй естественные речевые паттерны
- Поддерживай логическую связность
- Будь внимателен к незавершенным темам

Твой ответ (естественный, человечный, контекстно-осознанный):
"""
    return prompt

async def generate_ai_response(prompt, style):
    """Генерация ответа с учетом стиля"""
    temperature_map = {
        'active': 0.8,
        'reactive': 0.6,
        'balanced': 0.7,
        'deep': 0.75
    }
    
    temperature = temperature_map.get(style, 0.7)
    
    # Запрос к Yandex GPT
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": 2000
        },
        "messages": [
            {
                "role": "system",
                "text": "Ты опытный собеседник, ведущий естественную человеческую беседу."
            },
            {
                "role": "user",
                "text": prompt
            }
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(YANDEX_API_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['result']['alternatives'][0]['message']['text']
                else:
                    return "Давай поговорим о чем-то другом? Что тебя интересует?"
                    
    except Exception as e:
        logger.error(f"Ошибка Yandex GPT: {e}")
        return "Извини, я немного запуталась... Можешь повторить?"

async def context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать текущий контекст"""
    user_id = update.effective_user.id
    user_context = get_user_context(user_id)
    
    response = "📊 Текущий контекст беседы:\n\n"
    
    if 'deep_context' in user_context:
        dc = user_context['deep_context']
        response += f"🎯 Темы: {', '.join(list(dc.get('current_topics', {}).keys())[:3])}\n"
        response += f"📈 Настроение: {dc.get('emotional_arc', {}).get('current_mood', 0.5):.2f}\n"
        response += f"🏃 Темп: {dc.get('conversation_rhythm', {}).get('pace', 'medium')}\n"
        response += f"💭 Воспоминаний: {len(dc.get('historical_topics', {}))}\n"
    
    await update.message.reply_text(response)

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать память о беседе"""
    user_id = update.effective_user.id
    user_context = get_user_context(user_id)
    
    response = "🧠 Память о наших разговорах:\n\n"
    
    if 'deep_context' in user_context:
        dc = user_context['deep_context']
        historical = list(dc.get('historical_topics', {}).keys())
        if historical:
            response += "Исторические темы:\n"
            for topic in historical[:5]:
                response += f"• {topic}\n"
        else:
            response += "Еще нет сохраненных тем"
    
    await update.message.reply_text(response)

def main():
    """Основная функция"""
    # Проверка токенов
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден!")
        return
    
    # Инициализация базы данных
    UserDatabase()
    
    # Создание приложения
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("context", context_command))
    application.add_handler(CommandHandler("memory", memory_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message_with_deep_context))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Бот с глубоким контекстным анализом запускается...")
    
    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
