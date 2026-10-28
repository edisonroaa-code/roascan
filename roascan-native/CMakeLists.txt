cmake_minimum_required(VERSION 3.16)
project(roascan_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# Source files
set(ROASCAN_CORE_SOURCES
  src/roascan_preprocess.cpp
  src/roascan_segmentation.cpp
  src/roascan_fontmetrics.cpp
  src/roascan_lexicon.cpp
  src/roascan_c_api.cpp
)

# 1. Static library for internal tools & CLI
add_library(roascan_core_static STATIC ${ROASCAN_CORE_SOURCES})
set_target_properties(roascan_core_static PROPERTIES OUTPUT_NAME "roascan_core_static")
target_include_directories(roascan_core_static PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)

# 2. Shared dynamic library (roascan_core.dll / libroascan_core.so) for C-ABI / Python / .NET
add_library(roascan_core_shared SHARED ${ROASCAN_CORE_SOURCES})
set_target_properties(roascan_core_shared PROPERTIES OUTPUT_NAME "roascan_core")
target_include_directories(roascan_core_shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_compile_definitions(roascan_core_shared PRIVATE ROASCAN_CORE_EXPORTS)

# 3. CLI Executables
add_executable(roascan-preprocess src/main.cpp)
target_link_libraries(roascan-preprocess PRIVATE roascan_core_static)

add_executable(roascan-tool-lut src/tools/roascan_tool_lut.cpp)
target_link_libraries(roascan-tool-lut PRIVATE roascan_core_static)

add_executable(roascan-tool-lexicon src/tools/roascan_tool_lexicon.cpp)
target_link_libraries(roascan-tool-lexicon PRIVATE roascan_core_static)

add_executable(roascan-tool-fontmetrics src/tools/roascan_tool_fontmetrics.cpp)
target_link_libraries(roascan-tool-fontmetrics PRIVATE roascan_core_static)
