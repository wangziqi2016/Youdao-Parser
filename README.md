# Youdao-Parser
Parses YouDao online dictionary's result and display them on the terminal in a pretty form 

    Youdao Online Dictionary Parser
    ===============================

    Usage (without installing): python youdao_dict.py [word] [--options]
    Usage (after installation): define [word] [--options]

    The following must be used with [word] being the first argument

    -v/--verbose    Also show examples
    -g/--word-group Also show word group and their meanings
    -m5             Only Display the first 5 meaning of each word
    --debug         Shows debug message (e.g. reasons for parsing failure)
                    Used for developer to debug.
    --force         Ignore cached content
    --no-add        Do not add the word into the cache under all circumstances

    The following is used without specifying the [word]

    -h/--help         Display this message
    --install [dir]   Install this as an utility, "define". 
                      Optional argument specifies the location. 
    --uninstall       Uninstall the "define" utility. This removes the file returned
                      by executing "--ls-define", which is the installation path

    --trim-cache [#]  Remove cache contents until there are [#] of entry/-ies left
                      The number must be an integer greater than or equal to 0
                      Default value is 0, which means deleting all contents from 
                      the cache
    --ls-cache        List words in the cache. One word each line
    --ls-define       Print the absolute file name of the utility (i.e. the installation path)
    --ls-dir          Print the directory of this file

    -i/--interactive  Start in interactive mode; Press ESC to exit
