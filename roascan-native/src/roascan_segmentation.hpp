// roascan_segmentation.hpp
// RoaScan clean-room native engine: layout-aware block, line, and word segmentation.
// Uses recursive XY-Cut for multi-column/block reading order and typographic
// font-metric scaling for punctuation-aware word grouping.

#pragma once

#include "roascan_image.hpp"

#include <vector>

namespace roascan {

// Axis-aligned rectangle in pixel coordinates (right/bottom are exclusive).
struct Rect {
    int left = 0;
    int top = 0;
    int right = 0;
    int bottom = 0;

    int width() const { return right - left; }
    int height() const { return bottom - top; }
    bool valid() const { return right > left && bottom > top; }
};

// Segments a page into layout blocks/columns in natural reading order
// using recursive XY-Cut (horizontal block splits + vertical column valleys).
std::vector<Rect> segment_blocks(const GrayImage& binary);

// Segments text lines across the image in layout reading order (multi-column aware).
// Bands shorter than 'min_height' are dropped as noise.
std::vector<Rect> segment_lines(const GrayImage& binary, int min_height = 4);

// Segments words inside one line region using the vertical projection profile
// and dynamic typographical metrics.
std::vector<Rect> segment_words(const GrayImage& binary,
                                const Rect& line,
                                int gap = 8,
                                int min_width = 2);

// Draws a 1px gray border around each rectangle for visualization.
void draw_boxes(GrayImage& img, const std::vector<Rect>& boxes);

} // namespace roascan
