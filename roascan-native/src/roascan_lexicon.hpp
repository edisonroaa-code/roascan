// roascan_lexicon.hpp
// RoaScan clean-room native engine: Lexicon & Dictionary verification.

#pragma once

#include <string>
#include <string_view>
#include <vector>
#include <memory>
#include <unordered_map>

namespace roascan {

class Lexicon {
public:
    struct Node {
        bool is_terminal = false;
        std::unordered_map<char, std::unique_ptr<Node>> children;
    };

    Lexicon();
    ~Lexicon();

    void insert(std::string_view word);
    bool contains(std::string_view word) const;
    bool starts_with(std::string_view prefix) const;
    bool load_from_file(const std::string& filepath);
    std::size_t word_count() const { return count_; }
    std::vector<std::string> suggest(std::string_view word, int max_distance = 2) const;

private:
    std::unique_ptr<Node> root_;
    std::size_t count_ = 0;
};

} // namespace roascan
