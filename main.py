"""
Домашнее задание по веб-скрапингу для курса "Продвинутый Python" в Нетологии.
Парсинг статей с Хабра по ключевым словам с использованием изученных методов.
"""

import re
import sys
import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime

import requests
from bs4 import BeautifulSoup


# Определяем список ключевых слов:
KEYWORDS = ['дизайн', 'фото', 'web', 'python']

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    link: str
    date: str
    preview_text: str
    found_keywords: List[str]  # какие ключевые слова найдены


class HabrScraper:
    """
    Продвинутый скрапер для поиска статей на Хабре по ключевым словам.
    
    Использует методы, изученные в лекции:
    - Регулярные выражения для точного поиска
    - Обработка ошибок и retry логика
    - Логирование процесса
    - Продвинутые селекторы BeautifulSoup
    - Обработка различных форматов дат
    """

    def __init__(self, keywords: List[str], max_retries: int = 3):
        self.keywords = [kw.lower() for kw in keywords]
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        # Компилируем регулярные выражения для более быстрого поиска
        self.keyword_patterns = [
            re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE) 
            for keyword in self.keywords
        ]

    def _get_page_with_retry(self, url: str) -> str:
        """Получает HTML страницы с повторными попытками."""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Попытка {attempt + 1} получения страницы: {url}")
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                
                # Проверяем, что получили HTML
                if 'text/html' not in response.headers.get('content-type', ''):
                    logger.warning(f"Получен не HTML контент: {response.headers.get('content-type')}")
                
                logger.info(f"Страница успешно получена, размер: {len(response.text)} символов")
                return response.text
                
            except requests.RequestException as e:
                logger.error(f"Ошибка при получении страницы (попытка {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # экспоненциальная задержка
                    logger.info(f"Ожидание {wait_time} секунд перед повторной попыткой...")
                    time.sleep(wait_time)
                else:
                    logger.error("Все попытки исчерпаны")
                    return ""

    def _find_keywords_with_regex(self, text: str) -> List[str]:
        """Находит ключевые слова в тексте с помощью регулярных выражений."""
        found_keywords = []
        text_lower = text.lower()
        
        for i, pattern in enumerate(self.keyword_patterns):
            if pattern.search(text):
                found_keywords.append(self.keywords[i])
        
        return found_keywords

    def _parse_date(self, date_str: str) -> str:
        """Парсит и форматирует дату из различных форматов."""
        if not date_str:
            return "Дата не найдена"
        
        try:
            # Пробуем разные форматы дат
            date_formats = [
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d'
            ]
            
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    return parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # Если ничего не подошло, возвращаем первые 10 символов
            return date_str[:10] if len(date_str) >= 10 else date_str
            
        except Exception as e:
            logger.warning(f"Ошибка при парсинге даты '{date_str}': {e}")
            return date_str[:10] if len(date_str) >= 10 else "Дата не найдена"

    def _parse_article_preview(self, article_element) -> Optional[Article]:
        """Парсит превью одной статьи с улучшенной обработкой ошибок."""
        try:
            # Заголовок и ссылка - обновленные селекторы под новую структуру Хабра
            title_element = article_element.find('h2', class_='tm-title')
            if not title_element:
                logger.debug("Не найден заголовок статьи")
                return None
                
            title_link = title_element.find('a', class_='tm-title__link')
            if not title_link:
                logger.debug("Не найдена ссылка в заголовке")
                return None
                
            # Получаем текст из span внутри ссылки
            title_span = title_link.find('span')
            title = title_span.get_text(strip=True) if title_span else title_link.get_text(strip=True)
            if not title:
                logger.debug("Пустой заголовок статьи")
                return None
                
            link = title_link.get('href', '')
            if not link:
                logger.debug("Пустая ссылка статьи")
                return None
                
            # Формируем полную ссылку
            if not link.startswith('http'):
                link = 'https://habr.com' + link

            # Дата с улучшенным парсингом
            date_element = article_element.find('time')
            date_str = date_element.get('datetime', '') if date_element else ''
            formatted_date = self._parse_date(date_str)

            # Собираем preview текст из разных источников
            preview_parts = []
            
            # Заголовок
            preview_parts.append(title)
            
            # Основной текст превью - ищем в разных местах
            lead_elements = article_element.find_all('div', class_='tm-article-snippet__lead')
            for elem in lead_elements:
                text = elem.get_text(strip=True)
                if text:
                    preview_parts.append(text)
            
            # Также ищем в других возможных местах
            snippet_elements = article_element.find_all('div', class_='tm-article-body')
            for elem in snippet_elements:
                text = elem.get_text(strip=True)
                if text:
                    preview_parts.append(text)
            
            # Теги/хабы - обновленные селекторы
            tag_elements = article_element.find_all('a', class_='tm-article-snippet__hubs-item-link')
            for tag in tag_elements:
                tag_text = tag.get_text(strip=True)
                if tag_text:
                    preview_parts.append(tag_text)
            
            # Также ищем в других местах теги
            hub_elements = article_element.find_all('a', class_='tm-hub-link')
            for hub in hub_elements:
                hub_text = hub.get_text(strip=True)
                if hub_text:
                    preview_parts.append(hub_text)
            
            # Автор
            author_elements = article_element.find_all('a', class_='tm-user-info__username')
            for author in author_elements:
                author_text = author.get_text(strip=True)
                if author_text:
                    preview_parts.append(author_text)

            # Весь текст статьи для поиска
            full_text = article_element.get_text(strip=True)
            preview_parts.append(full_text)

            preview_text = ' '.join(preview_parts)
            
            # Ищем ключевые слова
            found_keywords = self._find_keywords_with_regex(preview_text)
            
            if not found_keywords:
                logger.debug(f"В статье '{title}' не найдены ключевые слова")
                return None

            logger.info(f"Найдена статья: '{title}' (ключевые слова: {found_keywords})")
            
            return Article(
                title=title,
                link=link,
                date=formatted_date,
                preview_text=preview_text,
                found_keywords=found_keywords
            )
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге статьи: {e}")
            return None

    def find_articles(self) -> List[Article]:
        """Находит статьи, содержащие ключевые слова."""
        url = "https://habr.com/ru/all/"
        logger.info(f"Начинаем поиск статей на {url}")
        
        html = self._get_page_with_retry(url)
        if not html:
            logger.error("Не удалось получить HTML страницы")
            return []

        soup = BeautifulSoup(html, 'html.parser')
        articles = []

        # Используем более точные селекторы
        article_elements = soup.find_all('article', class_='tm-articles-list__item')
        logger.info(f"Найдено {len(article_elements)} превью статей на странице")
        
        for i, article_element in enumerate(article_elements):
            logger.debug(f"Обрабатываем статью {i + 1}/{len(article_elements)}")
            article = self._parse_article_preview(article_element)
            if article:
                articles.append(article)

        logger.info(f"Итого найдено подходящих статей: {len(articles)}")
        return articles

    def print_articles(self, articles: List[Article]):
        """Выводит найденные статьи в требуемом формате."""
        if not articles:
            print("Статьи с заданными ключевыми словами не найдены.")
            return

        print(f"Найдено статей: {len(articles)}")
        print("-" * 100)
        
        for i, article in enumerate(articles, 1):
            keywords_str = ', '.join(article.found_keywords)
            print(f"{i}. {article.date} – {article.title} – {article.link}")
            print(f"   Найденные ключевые слова: {keywords_str}")
            print()

    def save_to_file(self, articles: List[Article], filename: str = "habr_articles.txt"):
        """Сохраняет результаты в файл."""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Найдено статей: {len(articles)}\n")
                f.write("=" * 100 + "\n\n")
                
                for i, article in enumerate(articles, 1):
                    f.write(f"{i}. {article.date} – {article.title} – {article.link}\n")
                    f.write(f"   Найденные ключевые слова: {', '.join(article.found_keywords)}\n")
                    f.write(f"   Превью: {article.preview_text[:200]}...\n\n")
            
            logger.info(f"Результаты сохранены в файл: {filename}")
            print(f"Результаты также сохранены в файл: {filename}")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении в файл: {e}")


def main():
    """Основная функция программы."""
    print("=" * 60)
    print("ПОИСК СТАТЕЙ НА ХАБРЕ ПО КЛЮЧЕВЫМ СЛОВАМ")
    print("=" * 60)
    print(f"Ключевые слова: {', '.join(KEYWORDS)}")
    print(f"Используются регулярные выражения для точного поиска")
    print(f"Логирование ведется в файл: scraper.log")
    print()
    
    logger.info("Запуск программы поиска статей на Хабре")
    logger.info(f"Ключевые слова для поиска: {KEYWORDS}")
    
    scraper = HabrScraper(KEYWORDS)
    articles = scraper.find_articles()
    
    scraper.print_articles(articles)
    scraper.save_to_file(articles)
    
    logger.info("Программа завершена")


if __name__ == "__main__":
    sys.exit(main())


