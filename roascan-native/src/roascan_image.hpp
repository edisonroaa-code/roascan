// roascan_image.hpp
// RoaScan clean-room native engine: minimal 8-bit grayscale image buffer.
//
// This is ORIGINAL code written for the RoaScan re-implementation. It does not
// wrap or depend on any proprietary binary. It uses only the C++ standard
// library and a trivial PGM (P5) loader/saver so the pipeline can be exercised
// without an external imaging library.

#pragma once

#include <cstdint>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace roascan {

// 8-bit grayscale image stored row-major.
struct GrayImage {
    int width = 0;
    int height = 0;
    std::vector<std::uint8_t> data;

    GrayImage() = default;
    GrayImage(int w, int h) : width(w), height(h), data(static_cast<std::size_t>(w) * h, 0) {}

    std::uint8_t& at(int x, int y) { return data[static_cast<std::size_t>(y) * width + x]; }
    const std::uint8_t& at(int x, int y) const { return data[static_cast<std::size_t>(y) * width + x]; }

    bool in_bounds(int x, int y) const {
        return x >= 0 && x < width && y >= 0 && y < height;
    }

    std::size_t pixel_count() const { return data.size(); }

    // --- PGM (P5) binary load/save -----------------------------------------

    static GrayImage load_pgm(const std::string& path) {
        std::ifstream f(path, std::ios::binary);
        if (!f) throw std::runtime_error("cannot open file: " + path);

        std::string magic;
        f >> magic;
        if (magic != "P5") throw std::runtime_error("not a P5 PGM file: " + path);

        int w = 0, h = 0, maxval = 0;
        f >> w >> h >> maxval;
        f.get(); // skip the single whitespace byte after maxval
        if (w <= 0 || h <= 0 || maxval <= 0 || maxval > 255)
            throw std::runtime_error("unsupported PGM header in: " + path);

        GrayImage img(w, h);
        f.read(reinterpret_cast<char*>(img.data.data()), static_cast<std::streamsize>(img.data.size()));
        if (f.gcount() != static_cast<std::streamsize>(img.data.size()))
            throw std::runtime_error("truncated PGM data in: " + path);
        return img;
    }

    void save_pgm(const std::string& path) const {
        std::ofstream f(path, std::ios::binary);
        if (!f) throw std::runtime_error("cannot write file: " + path);
        f << "P5\n" << width << " " << height << "\n255\n";
        f.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
    }
};

} // namespace roascan
