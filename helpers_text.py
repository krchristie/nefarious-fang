"""
helpers_text.py
===============

Text-fetching and parsing utilities used by the Gutenberg word-frequency
application. These functions are responsible for:

- Constructing the correct Project Gutenberg URL for a given book ID
- Downloading plain-text ebook content
- Extracting metadata such as title and author blocks
- Loading stopwords from file
- Tokenizing Gutenberg text and computing word frequencies

The module provides:

- :func:`make_gutenberg_link`
- :func:`fetch_gutenberg_text`
- :func:`extract_title`
- :func:`extract_author_block`
- :func:`load_stopwords`
- :class:`MyHTMLParser`

Notes
-----
This module performs no GUI operations and no logging; callers are responsible
for user-visible reporting.

Author: Karen R. Christie
CSM CIS 117 Final Project
Date: November–December 2025
"""

import re
import requests
from html.parser import HTMLParser
from collections import Counter
import string

STOPWORDS_PATH = "stopwords.txt"


def make_gutenberg_link(book_id):
    """
    Construct the direct text URL for a Project Gutenberg book.

    Accepts either:
        • an integer ID  (e.g. 5000)
        • a string with or without 'pg' prefix (e.g. '5000', 'pg5000')

    Parameters
    ----------
    book_id : int or str
        The Gutenberg numeric identifier.

    Returns
    -------
    str
        Fully formed URL pointing to the plain-text .txt file.
    """
    book_id = str(book_id).lower().replace("pg", "").strip()
    return f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"


def fetch_gutenberg_text(url, timeout=20):
    """
    Download the Gutenberg plain-text content from the given URL.

    Parameters
    ----------
    url : str
        URL of the .txt file.
    timeout : int, optional
        Network timeout in seconds.

    Returns
    -------
    (str or None, str or None)
        A pair (text, error_message).
        • text is the downloaded content if successful, else None.
        • error_message contains a user-friendly string if an error occurred.
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text, None
    except Exception as e:
        return None, f"Error fetching Gutenberg text: {e}"


def extract_title(text):
    """
    Extract the book title from Gutenberg metadata.

    Searches line-by-line for the first line beginning with 'Title:' (case-insensitive)
    and returns the remainder of that line.

    Parameters
    ----------
    text : str
        Entire Gutenberg book text.

    Returns
    -------
    str or None
        The extracted title, or None if no 'Title:' line is found.
    """
    for line in text.splitlines():
        low = line.lower().strip()
        if low.startswith("title:"):
            return line.split(":", 1)[1].strip()
    return None


def extract_author_block(text):
    """
    Extract the 'Author:' metadata block from Gutenberg text.

    Behavior
    --------
    1. Locate the first 'Author:' line (case-insensitive).
    2. Starting immediately after the 'Author:' tag, search for the next
       metadata-style header of the form:
           <letters and spaces>:
       (e.g., "Release Date:", "Language:", etc.)
    3. If such a header is found, return all text from 'Author:' up to
       (but not including) that header.
    4. Otherwise, return text from 'Author:' up to the next blank line.
    5. If neither a header nor a blank line is found, return all text from
       'Author:' to the end.

    Parameters
    ----------
    text : str
        Entire Gutenberg book text.

    Returns
    -------
    str or None
        The extracted author block beginning with 'Author:', or None if
        no 'Author:' header exists.
    """
    m = re.search(r'(?im)^[ \t]*author:\s*', text)
    if not m:
        return None

    start_idx = m.start()

    # Look for next metadata header (e.g. "Release Date:", "Language:")
    next_header = re.search(
        r'(?m)^[ \t]*[A-Za-z][A-Za-z \-]*:\s',
        text[m.end():]
    )

    if next_header:
        return text[start_idx:m.end() + next_header.start()].rstrip()

    # Fall back to finding the end of the block as the next blank line
    blank = text.find("\n\n", m.end())
    if blank != -1:
        return text[start_idx:blank].rstrip()

    # Or return all text from 'Author:' onward
    return text[start_idx:].rstrip()


def load_stopwords(filepath=STOPWORDS_PATH):
    """
    Load one stopword per line from a UTF-8 text file.

    Parameters
    ----------
    filepath : str
        Path to the stopwords file.

    Returns
    -------
    set[str]
        A set of lowercase stopwords. If the file cannot be loaded,
        an empty set is returned.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except Exception:
        return set()


class MyHTMLParser(HTMLParser):
    """
    Simple tokenizer/parser for Gutenberg text.

    Behavior:
    ----------
    • Splits incoming text into whitespace-separated tokens.
    • Removes punctuation around tokens.
    • Filters out tokens containing digits.
    • Accepts alphabetic words including internal apostrophes or hyphens.
    • Stores cleaned tokens in a list for later frequency calculation.

    Methods
    -------
    frequency(n, stopwords=None, top_k=None):
        Compute word frequencies using the stored tokens.
    """
    def __init__(self):
        super().__init__()
        self._words = []

    def handle_data(self, data):
        for token in data.split():
            cleaned = token.strip(string.punctuation)
            if not cleaned:
                continue
            # skip words containing digits
            if any(ch.isdigit() for ch in cleaned):
                continue

            # allow alphabetic words with '-' or apostrophes
            alphabetic = cleaned.replace("-", "").replace("'", "").isalpha()
            if alphabetic:
                self._words.append(cleaned.lower())


    def frequency(self, n, stopwords=None, top_k=None):
        """
        Compute word frequencies from the parsed tokens.

        Behavior
        --------
        • Counts all stored tokens using Counter.
        • Removes any words appearing in the stopwords set.
        • Keeps only words whose counts are >= n.
        • If top_k is provided, the filtered items are sorted by descending
          count and only the first top_k are returned.

        Parameters
        ----------
        n : int
            Minimum frequency required for a word to be included.
        stopwords : set[str], optional
            Words to exclude from counting.
        top_k : int or None
            If not None, return only the top_k highest-frequency items.
    
        Returns
        -------
        dict[str, int]
            A dictionary mapping each word to its frequency. If top_k is used,
            the result will contain at most top_k items, sorted by descending
            frequency order.
        """
        if stopwords is None:
            stopwords = set()

        counts = Counter(self._words)
        filtered = {
            w: c for w, c in counts.items()
            if c >= n and w not in stopwords
        }

        if top_k:
            top_items = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
            return dict(top_items[:top_k])

        return filtered
