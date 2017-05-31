
from bs4 import BeautifulSoup
import bs4
import requests
import sys
import os
import stat

def get_webpage(word):
    """
    This function returns a string which is the webpage of a given word
    Returns None if the return code is not HTTP status 200 which means an error
    happened
    
    :return: str/None 
    """
    url = "http://dict.youdao.com/search?le=eng&q=%s&keyfrom=dict2.index" % (word, )
    r = requests.get(url)
    if r.status_code != 200:
        return None

    return r.text

def parse_webpage(s):
    """
    Given the text of the webpage, parse it as an instance of a beautiful soup,
    using the default parser and encoding
    
    :param s: The text of the webpage 
    :return: beautiful soup object
    """
    return BeautifulSoup(s, 'html.parser')

def get_collins_dict(tree):
    """
    This function returns results by collins dictionary, given the beautiful soup
    tree object
    
    The return value is defined as follows: 
      
    {
      "word": "The word"
      "phonetic": "The pronunciation"
      "meanings": [
        {
          "category": "n. v. adj. adv. , etc.",
          "text": "Meaning of the word",
          "examples": [
            {
              "text": "Text of the example, with <b></b> being the keyword"
              "translation": "Translation of the text"
            },
          ]
        }, ...
      ]
    }
    
    :return: dict as specified as above, or None if fails
    """
    # This is the dict object we return to the caller
    ret = {}

    collins_result = tree.find(id="collinsResult")
    if isinstance(collins_result, bs4.element.Tag) is False:
        # it is not a valid div object (usually None if the tag does
        # not exist)
        return None
    elif collins_result.name != "div":
        # It is a valid tag, but the name is not div
        # This should be strange, though
        return None

    tree = collins_result

    # This <h4> contains the main word, the pronunciation
    h4 = tree.find("h4")
    if h4 is None:
        return None

    span_list = h4.find_all("span")
    if len(span_list) < 1:
        return None

    # This is the word we are looking for
    ret["word"] = span_list[0].text

    # This contains the phonetic
    em = h4.find("em")
    if em is None:
        return None
    # Save the phonetic (note: this is not ASCII)
    ret["phonetic"] = em.text
    # Initialize the meanings list
    ret["meanings"] = []

    # This is all meanings
    li_list = tree.find_all("li")
    for li in li_list:
        # Just add stuff into this dict object
        d = {}
        ret["meanings"].append(d)

        # The first <div> is word meaning, and all the rest are
        # examples and translations
        div_list = li.find_all("div")
        # Must be at least one div to show the meaning of the list
        if len(div_list) == 0:
            return None
        main_div = div_list[0]

        # Then find the <p> in the first div, which contains word category and
        # the meaning of the word
        p = main_div.find("p")
        if p is None:
            return None

        span = p.find("span")
        if span is None:
            return None

        # Save the category as category attribute
        d["category"] = span.text
        # Then for all text and child nodes in p, find the span
        # and then add all strings together after it
        start_concat = False
        meaning = ""
        for content in p.contents:
            if isinstance(content, bs4.element.Tag) is True and \
               content.name == "span":
                start_concat = True
                continue

            if start_concat is True:
                # for keywords in the article we manually surround them with
                # <b></b> tags
                if isinstance(content, bs4.element.Tag) is True and \
                   content.name == "b":
                    content = "<b>" + content.text + "</b>"

                content = content.strip()
                if len(content) == 0:
                    continue

                # Then use space to separate the contents
                meaning += (content + " ")

        # If we did not find anything then return
        if start_concat is False or \
           len(meaning) == 0:
            return None
        # Save the meaning of the word as the text
        d["text"] = meaning

        # Push examples into this list
        l = []
        d["examples"] = l
        # These are all examples
        for div in div_list[1:]:
            # Text is the first p and translation is the second p
            # We do not care the remaining <p>, but if there are less than
            # two then we simply return
            p_list = div.find_all("p")
            if len(p_list) < 2:
                return None

            l.append({
                "text": p_list[0].text.strip(),
                "translation": p_list[1].text.strip(),
            })


    return ret

RED_TEXT_START = "\033[1;31m"
RED_TEXT_END = "\033[0m"
def print_red(text):
    """
    Prints the given text in read fore color
    
    :param text: The text to be printed
    :return: None
    """
    sys.stdout.write(RED_TEXT_START)
    sys.stdout.write(text)
    sys.stdout.write(RED_TEXT_END)

def collins_pretty_print(d):
    """
    Prints a dict object in pretty form. The input dict object may
    be None, in which case we skip printing
    
    :return: None
    """
    global verbose_flag
    global m5_flag

    if d is None:
        return

    print_red(d["word"])
    sys.stdout.write("        ")
    sys.stdout.write(d["phonetic"])
    sys.stdout.write("\n")

    counter = 1
    for meaning in d["meanings"]:
        if m5_flag is True and counter == 6:
            return

        sys.stdout.write("%d. (%s) " % (counter, meaning["category"]))
        counter += 1

        text = meaning["text"]
        text = text.replace("<b>", RED_TEXT_START)
        text = text.replace("</b>", RED_TEXT_END)
        sys.stdout.write(text)

        sys.stdout.write("\n")

        if verbose_flag is True:
            for example in meaning["examples"]:
                sys.stdout.write("    - ")
                sys.stdout.write(example["text"])
                sys.stdout.write("\n")
                sys.stdout.write("      ")
                sys.stdout.write(example["translation"])
                sys.stdout.write("\n")

    sys.stdout.write("\n")

    return

INSTALL_FILE_NAME = "/usr/local/bin/define"
def install():
    """
    Installs a shortcut as "define" command for the current user using the pwd
    
    :return: None 
    """
    current_file = os.path.abspath(__file__)
    fp = open(INSTALL_FILE_NAME, "w")
    fp.write("#!/bin/bash\n")
    fp.write("python %s $@" % (current_file, ))
    fp.close()

    # Also usable by the user
    os.chmod(INSTALL_FILE_NAME, stat.S_IRWXO)

    print("Install successful")

    return

def uninstall():
    """
    This function uninstalls the "define" utility
    
    :return: None 
    """
    if os.path.isfile(INSTALL_FILE_NAME) is True:
        os.unlink(INSTALL_FILE_NAME)
        print("Uninstall successful")
    else:
        print("Did not find the utility - have to previously installed?")

    return

USAGE_STRING = """
Youdao Online Dictionary Parser
===============================

Usage: python youdao_dict.py [word] [options]

-h/--help    Display this message
-v/--verbose Also show examples
-m5          Only Display the first 5 meaning of each word

--install    Install this as an utility, "define". May need sudo
--uninstall  Uninstall the "define" utility. May need sudo
"""
verbose_flag = False
m5_flag = False

# In case the user put an option before the word
if len(sys.argv) >= 2 and \
   sys.argv[1][0] == "-" and \
   "install" not in sys.argv[1]:
    print(USAGE_STRING)
    sys.exit(0)

for arg in sys.argv:
    if arg == "-v" or arg == "--verbose":
        verbose_flag = True
    elif arg == "-m5":
        m5_flag = True
    elif arg == "-h" or arg == "--help":
        print(USAGE_STRING)
        sys.exit(0)
    elif arg == "--install":
        install()
        sys.exit(0)
    elif arg == "--uninstall":
        uninstall()
        sys.exit(0)

collins_pretty_print(get_collins_dict(parse_webpage(get_webpage(sys.argv[1]))))