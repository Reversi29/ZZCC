# Project-level configuration.
cmake_minimum_required(VERSION 3.14)
project(zzcc LANGUAGES CXX)

# The name of the executable created for the application. Change this to change
# the on-disk name of your application.
set(BINARY_NAME "zzcc")

# Explicitly opt in to modern CMake behaviors to avoid warnings with recent
# versions of CMake.
cmake_policy(VERSION 3.14...3.25)

include(FetchContent)

# 设置使用 .NET SDK 中的 NuGet
set(USE_DOTNET_NUGET ON)

# 设置 NuGet 路径（使用 .NET SDK 中的 NuGet）
find_program(NUGET_EXE NAMES nuget nuget.exe dotnet
  PATHS
    "$ENV{ProgramFiles}/dotnet"
    "$ENV{ProgramFiles_x86}/dotnet"
    "$ENV{USERPROFILE}/.dotnet/tools"
  PATH_SUFFIXES dotnet
  DOC "Path to NuGet executable")

if(NOT NUGET_EXE)
  message(FATAL_ERROR "NuGet not found! Install .NET SDK or NuGet CLI.")
else()
  message(STATUS "Found NuGet: ${NUGET_EXE}")
  # 设置环境变量让Flutter插件能访问
  set(ENV{NUGET} "${NUGET_EXE}")
  set(ENV{UseDotNetNuGet} "true")
  
  # 关键修复：确保NuGet路径在插件构建时可用
  set(NUGET_EXE "${NUGET_EXE}" CACHE INTERNAL "Path to NuGet executable" FORCE)
endif()

# 设置 NuGet 命令使用 .NET SDK 中的 NuGet
set(NUGET_COMMAND "${NUGET_EXE}" "nuget")

# Define build configuration option.
get_property(IS_MULTICONFIG GLOBAL PROPERTY GENERATOR_IS_MULTI_CONFIG)
if(IS_MULTICONFIG)
  set(CMAKE_CONFIGURATION_TYPES "Debug;Profile;Release"
    CACHE STRING "" FORCE)
else()
  if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE "Debug" CACHE
      STRING "Flutter build mode" FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS
      "Debug" "Profile" "Release")
  endif()
endif()
# Define settings for the Profile build mode.
set(CMAKE_EXE_LINKER_FLAGS_PROFILE "${CMAKE_EXE_LINKER_FLAGS_RELEASE}")
set(CMAKE_SHARED_LINKER_FLAGS_PROFILE "${CMAKE_SHARED_LINKER_FLAGS_RELEASE}")
set(CMAKE_C_FLAGS_PROFILE "${CMAKE_C_FLAGS_RELEASE}")
set(CMAKE_CXX_FLAGS_PROFILE "${CMAKE_CXX_FLAGS_RELEASE}")

# Use Unicode for all projects.
add_definitions(-DUNICODE -D_UNICODE)

# Compilation settings that should be applied to most targets.
#
# Be cautious about adding new options here, as plugins use this function by
# default. In most cases, you should add new options to specific targets instead
# of modifying this function.
function(APPLY_STANDARD_SETTINGS TARGET)
  target_compile_features(${TARGET} PUBLIC cxx_std_17)
  target_compile_options(${TARGET} PRIVATE /W4 /WX /wd"4100")
  target_compile_options(${TARGET} PRIVATE /EHsc)
  target_compile_definitions(${TARGET} PRIVATE "_HAS_EXCEPTIONS=0")
  target_compile_definitions(${TARGET} PRIVATE "$<$<CONFIG:Debug>:_DEBUG>")
endfunction()

# Flutter library and tool build rules.
set(FLUTTER_MANAGED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/flutter")
add_subdirectory(${FLUTTER_MANAGED_DIR})

# Application build; see runner/CMakeLists.txt.
add_subdirectory("runner")


# Generated plugin build rules, which manage building the plugins and adding
# them to the application.
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/flutter/generated_plugins.cmake)
    include(${CMAKE_CURRENT_SOURCE_DIR}/flutter/generated_plugins.cmake)

    # 禁用插件中的特定警告
    if(TARGET flutter_inappwebview_windows_plugin)
        target_compile_options(flutter_inappwebview_windows_plugin PRIVATE
            /wd4244   # 禁用64位转32位警告
            /wd4458   # 禁用变量隐藏警告
        )
    endif()
else()
    message(WARNING "Generated plugins file not found")
endif()


# === Installation ===
# Support files are copied into place next to the executable, so that it can
# run in place. This is done instead of making a separate bundle (as on Linux)
# so that building and running from within Visual Studio will work.
set(BUILD_BUNDLE_DIR "$<TARGET_FILE_DIR:${BINARY_NAME}>")
# Make the "install" step default, as it's required to run.
set(CMAKE_VS_INCLUDE_INSTALL_TO_DEFAULT_BUILD 1)
if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
  set(CMAKE_INSTALL_PREFIX "${BUILD_BUNDLE_DIR}" CACHE PATH "..." FORCE)
endif()

set(INSTALL_BUNDLE_DATA_DIR "${CMAKE_INSTALL_PREFIX}/data")
set(INSTALL_BUNDLE_LIB_DIR "${CMAKE_INSTALL_PREFIX}")

install(TARGETS ${BINARY_NAME} RUNTIME DESTINATION "${CMAKE_INSTALL_PREFIX}"
  COMPONENT Runtime)

install(FILES "${FLUTTER_ICU_DATA_FILE}" DESTINATION "${INSTALL_BUNDLE_DATA_DIR}"
  COMPONENT Runtime)

install(FILES "${FLUTTER_LIBRARY}" DESTINATION "${INSTALL_BUNDLE_LIB_DIR}"
  COMPONENT Runtime)

if(PLUGIN_BUNDLED_LIBRARIES)
  install(FILES "${PLUGIN_BUNDLED_LIBRARIES}"
    DESTINATION "${INSTALL_BUNDLE_LIB_DIR}"
    COMPONENT Runtime)
endif()

# Copy the native assets provided by the build.dart from all packages.
set(NATIVE_ASSETS_DIR "${PROJECT_BUILD_DIR}native_assets/windows/")
install(DIRECTORY "${NATIVE_ASSETS_DIR}"
   DESTINATION "${INSTALL_BUNDLE_LIB_DIR}"
   COMPONENT Runtime)

# Fully re-copy the assets directory on each build to avoid having stale files
# from a previous install.
set(FLUTTER_ASSET_DIR_NAME "flutter_assets")
install(CODE "
  file(REMOVE_RECURSE \"${INSTALL_BUNDLE_DATA_DIR}/${FLUTTER_ASSET_DIR_NAME}\")
  " COMPONENT Runtime)
install(DIRECTORY "${PROJECT_BUILD_DIR}/${FLUTTER_ASSET_DIR_NAME}"
  DESTINATION "${INSTALL_BUNDLE_DATA_DIR}" COMPONENT Runtime)

# Install the AOT library on non-Debug builds only.
install(FILES "${AOT_LIBRARY}" DESTINATION "${INSTALL_BUNDLE_DATA_DIR}"
  CONFIGURATIONS Profile;Release
  COMPONENT Runtime)

# 设置 vcpkg 工具链和 manifest
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/vcpkg_path.txt")
  file(READ "${CMAKE_CURRENT_SOURCE_DIR}/scripts/vcpkg_path.txt" VCPKG_ROOT_PATH)
  string(STRIP "${VCPKG_ROOT_PATH}" VCPKG_ROOT_PATH)
  set(CMAKE_TOOLCHAIN_FILE  "${VCPKG_ROOT_PATH}/scripts/buildsystems/vcpkg.cmake"
      CACHE STRING "Vcpkg toolchain file")
  
  # 启用 manifest 模式
  set(VCPKG_MANIFEST_DIR "${CMAKE_CURRENT_SOURCE_DIR}/windows" CACHE STRING "Vcpkg manifest directory")
  set(VCPKG_MANIFEST_MODE ON CACHE BOOL "Enable Vcpkg manifest mode")

  set(VCPKG_TARGET_TRIPLET "x64-windows" CACHE STRING "Vcpkg target triplet")
endif()

if(NOT DEFINED VCPKG_MANIFEST_DIR)
    # 默认为当前目录
    set(VCPKG_MANIFEST_DIR "${CMAKE_CURRENT_SOURCE_DIR}"
        CACHE STRING "Local Vcpkg manifest directory")
    set(VCPKG_MANIFEST_MODE ON CACHE BOOL "Enable local Vcpkg manifest mode")
endif()

message(STATUS "Using Vcpkg manifest: ${VCPKG_MANIFEST_DIR}/vcpkg.json")
message(STATUS "Vcpkg root: ${VCPKG_ROOT_PATH}")
message(STATUS "Target triplet: ${VCPKG_TARGET_TRIPLET}")
message(STATUS "Windows build using manifest from: ${VCPKG_MANIFEST_DIR}")

# # 查找依赖
# find_package(LibtorrentRasterbar CONFIG REQUIRED)
# find_package(Boost COMPONENTS system chrono random REQUIRED)

# # 添加可执行文件
# add_executable(${BINARY_NAME} WIN32
#     # ... 源文件列表 ...
# )

# 链接库
# target_link_libraries(${BINARY_NAME} PRIVATE
#     "${CMAKE_SOURCE_DIR}/native/windows/torrent/torrent_ffi.lib"
#     # LibtorrentRasterbar::torrent-rasterbar
#     # Boost::system
#     # Boost::chrono
#     # Boost::random
# )

# 复制 DLL 文件到输出目录
add_custom_target(CopyDlls ALL
    COMMAND ${CMAKE_COMMAND} -E chdir "${CMAKE_CURRENT_SOURCE_DIR}" "copy_dlls.bat"
    COMMENT "Copying DLL files using batch script"
)

add_dependencies(${BINARY_NAME} CopyDlls)

# # 设置运行时库
# if(MSVC)
#     set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
# endif()

# # 添加下载依赖的自定义目标
# if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/vcpkg" OR 
#    NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/native/windows/libtorrent.dll")
#     add_custom_target(download_dependencies
#         COMMAND powershell -ExecutionPolicy Bypass -File "${CMAKE_CURRENT_SOURCE_DIR}/scripts/download_dependencies.ps1"
#         COMMENT "Downloading libtorrent and Boost dependencies"
#         WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
#     )
    
#     add_dependencies(${BINARY_NAME} download_dependencies)
# endif()