# Youdao-Parser
Parses YouDao online dictionary's result and display them on the terminal in a pretty form

    Usage: python youdao_dict.py [word] [options]

    The following must be used with [word] being the first argument

    -h/--help    Display this message
    -v/--verbose Also show examples
    -m5          Only Display the first 5 meaning of each word
    --debug      Shows debug message (e.g. reasons for parsing failure)
                 Used for developer to debug.
    --force      Ignore cached content

    The following is used without specifying the [word]

    --install  [dir]  Install this as an utility, "define". 
                      Optional argument specifies the location. 
    --uninstall       Uninstall the "define" utility. This removes the first "define"
                      utility that appears under PATH
    --cd              Print the directory of this file
