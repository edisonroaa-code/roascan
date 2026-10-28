// main.cpp
// RoaScan clean-room native engine: preprocessing + segmentation CLI.
//
// Usage:
//   roascan-preprocess <input.pgm> <output.pgm> [--binarize otsu|sauvola]
//                    [--no-deskew] [--min-area N] [--word-gap N] [--boxes <path>]
//
// Loads an 8-bit PGM, binarizes, corrects skew, removes speckle, segments
// lines and words, and writes the foreground mask (255 = ink) as a PGM.

#include "roascan_preprocess.hpp"
#include "roascan_segmentation.hpp"

#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: roascan-preprocess <input.pgm> <output.pgm> "
                     "[--binarize otsu|sauvola] [--no-deskew] [--min-area N] "
                     "[--word-gap N] [--boxes <path>]\n";
        return 2;
    }

    std::string input = argv[1];
    std::string output = argv[2];
    std::string boxes_path;
    std::string binarize = "sauvola";
    bool deskew = true;
    int min_area = 12;
    int word_gap = 8;

    for (int i = 3; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--binarize" && i + 1 < argc) {
            binarize = argv[++i];
        } else if (a == "--no-deskew") {
            deskew = false;
        } else if (a == "--min-area" && i + 1 < argc) {
            min_area = std::atoi(argv[++i]);
        } else if (a == "--word-gap" && i + 1 < argc) {
            word_gap = std::atoi(argv[++i]);
        } else if (a == "--boxes" && i + 1 < argc) {
            boxes_path = argv[++i];
        }
    }

    roascan::GrayImage img = roascan::GrayImage::load_pgm(input);
    std::printf("loaded %dx%d grayscale image\n", img.width, img.height);

    roascan::GrayImage binary;
    if (binarize == "otsu") {
        const int t = roascan::otsu_threshold(img);
        std::printf("otsu threshold = %d\n", t);
        binary = roascan::binarize_otsu(img, t);
    } else {
        binary = roascan::binarize_sauvola(img, 15, 0.34, 128.0);
        std::printf("binarized with Sauvola adaptive threshold\n");
    }

    if (deskew) {
        const double angle = roascan::detect_skew_degrees(binary, -10.0, 10.0, 0.5);
        std::printf("detected skew = %.2f deg\n", angle);
        if (std::abs(angle) > 0.25) {
            binary = roascan::rotate(binary, -angle);
            std::printf("deskewed by rotating %.2f deg\n", -angle);
        }
    }

    binary = roascan::despeckle(binary, min_area);
    std::printf("despeckled (min component area = %d px)\n", min_area);

    // --- Segmentation ------------------------------------------------------
    const auto lines = roascan::segment_lines(binary);
    std::printf("segmented %zu lines\n", lines.size());
    for (std::size_t li = 0; li < lines.size(); ++li) {
        const auto& ln = lines[li];
        const auto words = roascan::segment_words(binary, ln, word_gap);
        std::printf("  line %zu: y=[%d,%d) -> %zu words\n", li, ln.top, ln.bottom, words.size());
        for (std::size_t wi = 0; wi < words.size(); ++wi) {
            const auto& wd = words[wi];
            std::printf("    word %zu: x=[%d,%d) y=[%d,%d)\n",
                        wi, wd.left, wd.right, wd.top, wd.bottom);
        }
    }

    if (!boxes_path.empty()) {
        roascan::GrayImage viz = binary;
        std::vector<roascan::Rect> all_words;
        for (const auto& ln : lines) {
            for (const auto& wd : roascan::segment_words(binary, ln, word_gap)) {
                all_words.push_back(wd);
            }
        }
        roascan::draw_boxes(viz, all_words);
        viz.save_pgm(boxes_path);
        std::printf("wrote segmentation visualization to %s\n", boxes_path.c_str());
    }

    binary.save_pgm(output);
    std::printf("wrote %dx%d result to %s\n", binary.width, binary.height, output.c_str());
    return 0;
}
