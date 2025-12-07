"""
helpers_text
============

Text-fetching and parsing utilities for the Project Gutenberg word-frequency
application.

This module provides functions for constructing Gutenberg URLs, downloading
plain-text ebook content, extracting high-level metadata such as title and
author blocks, loading stopwords, and tokenizing raw text for frequency
analysis. These routines are pure text utilities and contain no GUI or
database logic.

Available functions and classes
-------------------------------
- :func:`make_gutenberg_link`  
    Construct the canonical URL for a Project Gutenberg plain-text file.

- :func:`fetch_gutenberg_text`  
    Download ebook text with simple error handling.

- :func:`extract_title`  
    Retrieve the book title from standard Gutenberg metadata.

- :func:`extract_author_block`  
    Extract the author section from Gutenberg header information.

- :func:`load_stopwords`  
    Load stopwords from a UTF-8 text file.

- :class:`MyHTMLParser`  
    A lightweight HTMLParser subclass for tokenizing words and computing
    frequency counts.

Notes
-----
- This module performs **no GUI operations and no logging**. 
  All user-visible reporting must be handled by the caller.
- All functions operate on plain Unicode text and make minimal assumptions
  about Gutenberg formatting beyond common metadata conventions.

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
    Construct the canonical Project Gutenberg text URL for a book.

    The function accepts either an integer or a string ID (with or without
    a leading ``"pg"`` prefix) and normalizes it to the numeric form used
    by Gutenberg's plain-text endpoints.

    Parameters
    ----------
    book_id : int or str
        Project Gutenberg numeric identifier.

    Returns
    -------
    str
        Fully formed URL pointing to the plain-text ``.txt`` file for the
        specified book.
    """
    book_id = str(book_id).lower().replace("pg", "").strip()
    return f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"

def fetch_gutenberg_text(url, timeout=20):
    """
    Retrieve plain-text book content from a Project Gutenberg URL.

    A simple wrapper around :func:`requests.get` that provides error handling
    suitable for user-facing applications. Network failures, HTTP errors, and
    unexpected exceptions are returned as a human-readable message rather than
    raised.

    Parameters
    ----------
    url : str
        Direct URL to a Gutenberg ``.txt`` file.
    timeout : int, optional
        Connection timeout in seconds. Default is 20.

    Returns
    -------
    tuple
        ``(text, error_message)``  
        - ``text`` is a string containing the downloaded content, or ``None``  
          if the request failed.  
        - ``error_message`` is ``None`` on success, otherwise a descriptive  
          message suitable for display in the GUI.
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text, None
    except Exception as e:
        return None, f"Error fetching Gutenberg text: {e}"

def extract_title(text):
    """
    Extract the book title from Gutenberg header metadata.

    The function scans the text line-by-line for the first line beginning with
    ``"Title:"`` (case-insensitive) and returns the portion following the colon.
    Only the first occurrence is considered.

    Parameters
    ----------
    text : str
        Full Gutenberg ebook text.

    Returns
    -------
    str or None
        The extracted title, or ``None`` if no recognizable ``"Title:"`` header
        is present.
    """
    for line in text.splitlines():
        low = line.lower().strip()
        if low.startswith("title:"):
            return line.split(":", 1)[1].strip()
    return None


def extract_author_block(text):
    """
    Extract the author metadata block from Gutenberg header content.

    Behavior
    --------
    1. Search for the first ``"Author:"`` header (case-insensitive).  
    2. After locating this header, look ahead for the next metadata-style
       header of the form  
       ``<letters and spaces>:``,  
       such as ``"Release Date:"`` or ``"Language:"``.  
    3. If found, return the text from ``"Author:"`` up to—but not including—
       that header.  
    4. If no later header is detected, fall back to returning text up to the
       next blank line.  
    5. If neither is available, return all remaining text starting at the
       ``"Author:"`` line.

    Parameters
    ----------
    text : str
        Full Gutenberg ebook text.

    Returns
    -------
    str or None
        The extracted author metadata block beginning with ``"Author:"``,
        or ``None`` if no such header is present.
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
    Load stopwords from a UTF-8 text file, one word per line.

    Blank lines are ignored. All stopwords are normalized to lowercase.

    Parameters
    ----------
    filepath : str, optional
        Path to a stopwords file. Defaults to the module-level
        ``STOPWORDS_PATH``.

    Returns
    -------
    set of str
        A set of lowercase stopwords. If the file cannot be read (e.g. missing
        or unreadable), an empty set is returned.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except Exception:
        return set()

class MyHTMLParser(HTMLParser):
    """
    Lightweight tokenizer for Gutenberg text based on :class:`HTMLParser`.

    The parser extracts word-like tokens from raw text. Punctuation is stripped,
    digits are excluded, and alphabetic words containing internal hyphens or
    apostrophes are permitted. Cleaned tokens are stored internally for later
    frequency computation.

    Notes
    -----
    This class does not attempt to interpret HTML structure; it simply uses
    :class:`HTMLParser` to receive text segments and tokenize them.

    Methods
    -------
    handle_data(data)
        Tokenize and accumulate cleaned words from a text segment.
    frequency(n, stopwords=None, top_k=None)
        Compute filtered word frequencies from accumulated tokens.
    """
    def __init__(self):
        super().__init__()
        self._words = []
       
    def handle_data(self, data):
        """
        Tokenize a chunk of text delivered by :class:`HTMLParser`.

        Processing steps:
        - Split on whitespace.
        - Strip leading and trailing punctuation.
        - Exclude tokens containing digits.
        - Allow alphabetic words with internal apostrophes or hyphens.
        - Normalize to lowercase and append to the internal token list.
        """
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
        Compute word frequencies from accumulated tokens.

        The method applies a minimum-count threshold, removes stopwords, and
        optionally returns only the highest-frequency results.

        Parameters
        ----------
        n : int
            Minimum frequency threshold for a word to be included.
        stopwords : set of str, optional
            Set of words to exclude from the results. Default is an empty set.
        top_k : int or None, optional
            If provided, return only the ``top_k`` most frequent items,
            sorted by descending frequency.

        Returns
        -------
        dict
            Mapping of ``word → count`` that satisfies the threshold and
            filtering conditions. When ``top_k`` is supplied, the returned
            dictionary contains at most ``top_k`` items, ordered by decreasing
            frequency.
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
