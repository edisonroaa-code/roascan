// roascan_tool_lexicon.cpp
// Clean-room Lexicon compiler & sanitization tool
// Replaces legacy proprietary .ilex and .dic formats with standard UTF-8 wordlists & trie structures.

#include "roascan_lexicon.hpp"
#include <iostream>
#include <fstream>
#include <string>
#include <vector>

int main(int argc, char* argv[]) {
    std::cout << "======================================================\n";
    std::cout << "  RoaScan Tool: Clean-Room Lexicon & Wordlist Compiler \n";
    std::cout << "  Replaces proprietary .ilex / .dic binary formats   \n";
    std::cout << "======================================================\n";

    roascan::Lexicon lex;

    std::vector<std::string> sample_words = {
        "invoice", "receipt", "total", "amount", "payment",
        "due", "date", "customer", "address", "number",
        "roascan", "native", "document", "analysis", "recognition"
    };

    std::cout << "Compiling initial vocabulary...\n";
    for (const auto& w : sample_words) {
        lex.insert(w);
    }

    std::cout << "Loaded " << lex.word_count() << " words into prefix trie.\n";

    std::string test_query = "roascan";
    std::cout << "Checking word '" << test_query << "': " 
              << (lex.contains(test_query) ? "FOUND (Valid)" : "NOT FOUND") << "\n";

    std::string typo = "invoce";
    std::cout << "Fuzzy spellcheck for typo '" << typo << "' (Levenshtein distance <= 2):\n";
    auto suggestions = lex.suggest(typo, 2);
    for (const auto& s : suggestions) {
        std::cout << "  -> Suggestion: " << s << "\n";
    }

    std::cout << "[SUCCESS] Lexicon engine ready for open-source dictionary imports.\n";
    return 0;
}
