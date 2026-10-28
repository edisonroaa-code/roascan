// roascan_preprocess.hpp
// RoaScan clean-room native engine: image preprocessing (brightness/contrast,
// binarization, coarse-to-fine skew detection, bilinear/nearest rotation,
// connected-component despeckle).

#pragma once

#include "roascan_image.hpp"

namespace roascan {

// Adjusts brightness and contrast using normalized 8-bit parameters (0..255),
// where 128 is neutral (no change) for both brightness and contrast.
GrayImage adjust_brightness_contrast(const GrayImage& img,
                                     int brightness = 128,
                                     int contrast = 128);

// Computes the global Otsu threshold for a grayscale image.
int otsu_threshold(const GrayImage& img);

// Global binarization using Otsu (or explicit threshold 0..255). Returns 0/255 image.
GrayImage binarize_otsu(const GrayImage& img, int threshold = -1);

// Local adaptive binarization (Sauvola) using 64-bit integer integral images.
// 'window' is the odd square window size, 'k' is the sensitivity constant
// (typical 0.2 .. 0.5), 'r' is the dynamic-range constant (128 for 8-bit).
GrayImage binarize_sauvola(const GrayImage& img, int window = 15, double k = 0.34, double r = 128.0);

// Detects the dominant skew angle (degrees) of a binary image by maximizing
// the variance of the horizontal projection profile via coarse-to-fine search
// over subsampled foreground points. Binary pixels: 0 (background) / 255 (ink).
double detect_skew_degrees(const GrayImage& binary,
                           double min_angle = -15.0,
                           double max_angle = 15.0,
                           double step = 0.1);

// Rotates an image by the given angle (degrees) about its center using
// nearest-neighbor sampling (ideal for binary masks). Positive = CCW.
GrayImage rotate(const GrayImage& img, double angle_deg, std::uint8_t fill = 0);

// Rotates a grayscale image by the given angle (degrees) about its center using
// bilinear interpolation (ideal for grayscale images before cropping).
GrayImage rotate_bilinear(const GrayImage& img, double angle_deg, std::uint8_t fill = 255);

// Removes connected foreground components whose area (pixel count) is below
// 'min_area'. 8-connectivity. Binary image: 0 background, 255 foreground.
GrayImage despeckle(const GrayImage& binary, int min_area = 12);

// Enhances a grayscale document scan using its cleaned binary foreground mask:
// whitens noisy/shadowed background to pure white (255) while preserving smooth
// anti-aliased grayscale glyph edges and darkening faded ink strokes.
GrayImage enhance_document(const GrayImage& gray, const GrayImage& clean_binary);

// Removes horizontal and vertical table grid lines from a binary image (0=bg, 255=ink)
// while preserving character strokes that touch or cross the grid lines.
GrayImage remove_table_grid_lines(const GrayImage& binary,
                                  int min_horiz_len = 0,
                                  int min_vert_len = 0);

// Performs lossless orthogonal rotation by 90 (CCW), 180, or 270 (CW) degrees.
GrayImage rotate_orthogonal(const GrayImage& img, int degrees);

// Detects whether a binary document page is rotated sideways (90/270 deg) vs
// horizontal (0/180 deg) by comparing normalized horizontal and vertical
// projection profile variances. Returns 90 if sideways, 0 otherwise.
int detect_sideways_orientation(const GrayImage& binary);

} // namespace roascan
