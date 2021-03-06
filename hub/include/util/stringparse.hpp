#include <string>
#include <iostream>
#include <algorithm>
#include <functional> 
#include <cctype>
#include <locale>

#ifndef SLUMBER_STRINGPARSE_H
#define SLUMBER_STRINGPARSE_H

namespace stringparse {

//Start trimmer
static inline std::string ltrim(std::string s) {
    s.erase(s.begin(), std::find_if(s.begin(), s.end(),
            std::not1(std::ptr_fun<int, int>(std::isspace))));
    return s;
}

//End trimmer
static inline std::string rtrim(std::string s) {
    s.erase(std::find_if(s.rbegin(), s.rend(),
            std::not1(std::ptr_fun<int, int>(std::isspace))).base(), s.end());
    return s;
}

//Trim from both ends
static inline std::string trim(std::string s) {
    return ltrim(rtrim(s));
}

}

#endif
