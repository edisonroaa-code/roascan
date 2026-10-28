// roascan_lexicon.cpp
// RoaScan clean-room native engine: Lexicon & Dictionary verification implementation
// with incremental Trie Levenshtein DP and branch pruning.

#include "roascan_lexicon.hpp"
#include <fstream>
#include <algorithm>
#include <numeric>

namespace roascan {

Lexicon::Lexicon() : root_(std::make_unique<Node>()) {}

Lexicon::~Lexicon() = default;

void Lexicon::insert(std::string_view word) {
    if (word.empty()) return;
    Node* current = root_.get();
    for (char c : word) {
        auto it = current->children.find(c);
        if (it == current->children.end()) {
            auto next = std::make_unique<Node>();
            Node* next_ptr = next.get();
            current->children.emplace(c, std::move(next));
            current = next_ptr;
        } else {
            current = it->second.get();
        }
    }
    if (!current->is_terminal) {
        current->is_terminal = true;
        count_++;
    }
}

bool Lexicon::contains(std::string_view word) const {
    if (word.empty()) return false;
    const Node* current = root_.get();
    for (char c : word) {
        auto it = current->children.find(c);
        if (it == current->children.end()) {
            return false;
        }
        current = it->second.get();
    }
    return current && current->is_terminal;
}

bool Lexicon::starts_with(std::string_view prefix) const {
    const Node* current = root_.get();
    for (char c : prefix) {
        auto it = current->children.find(c);
        if (it == current->children.end()) {
            return false;
        }
        current = it->second.get();
    }
    return true;
}

bool Lexicon::load_from_file(const std::string& filepath) {
    std::ifstream file(filepath);
    if (!file.is_open()) return false;

    std::string line;
    while (std::getline(file, line)) {
        // Support both plain wordlists and Hunspell .dic ("word/FLAGS")
        auto slash_pos = line.find('/');
        if (slash_pos != std::string::npos) {
            line.resize(slash_pos);
        }
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t')) {
            line.pop_back();
        }
        if (!line.empty()) {
            insert(line);
        }
    }
    return true;
}

namespace {

// Incremental Trie Levenshtein search with early subtree pruning:
// Computes only 1 DP row per Trie edge and prunes whenever min(curr_row) > max_dist.
void search_trie_dp(const Lexicon::Node* node,
                    char ch,
                    std::string& current_word,
                    std::string_view target,
                    const std::vector<int>& prev_row,
                    int max_dist,
                    std::vector<std::pair<int, std::string>>& scored_results) {
    const std::size_t n = target.size();
    std::vector<int> curr_row(n + 1);
    curr_row[0] = prev_row[0] + 1;

    int row_min = curr_row[0];
    for (std::size_t j = 1; j <= n; ++j) {
        const int insert_cost = curr_row[j - 1] + 1;
        const int delete_cost = prev_row[j] + 1;
        const int replace_cost = prev_row[j - 1] + ((target[j - 1] == ch) ? 0 : 1);
        curr_row[j] = std::min({insert_cost, delete_cost, replace_cost});
        if (curr_row[j] < row_min) {
            row_min = curr_row[j];
        }
    }

    if ( node->is_terminal && curr_row[n] <= max_dist ) {
        scored_results.emplace_back(curr_row[n], current_word);
    }

    // Early branch pruning: if no cell in curr_row is <= max_dist, no descendant can match.
    if (row_min <= max_dist) {
        for (const auto& [next_ch, child] : node->children) {
            current_word.push_back(next_ch);
            search_trie_dp(child.get(), next_ch, current_word, target, curr_row, max_dist, scored_results);
            current_word.pop_back();
        }
    }
}

} // namespace

std::vector<std::string> Lexicon::suggest(std::string_view word, int max_distance) const {
    if (!root_ || max_distance < 0) return {};

    const std::size_t n = word.size();
    std::vector<int> init_row(n + 1);
    std::iota(init_row.begin(), init_row.end(), 0);

    std::vector<std::pair<int, std::string>> scored;
    std::string current;
    current.reserve(n + max_distance + 2);

    for (const auto& [ch, child] : root_->children) {
        current.push_back(ch);
        search_trie_dp(child.get(), ch, current, word, init_row, max_distance, scored);
        current.pop_back();
    }

    std::sort(scored.begin(), scored.end(), [](const auto& a, const auto& b) {
        if (a.first != b.first) return a.first < b.first;
        return a.second < b.second;
    });

    std::vector<std::string> results;
    results.reserve(scored.size());
    for (auto& [dist, cand] : scored) {
        results.push_back(std::move(cand));
    }
    return results;
}

} // namespace roascan
