# M46 (D-084): write the export list of ffmpeg.dll from the static libavutil / libavcodec archives.
#
# Upstream FFmpeg exports, for each library, the symbols matching "av*" and hides the rest (libavutil/libavutil.v,
# libavcodec/libavcodec.v). This script does the same for the single DLL that holds both archives: every external
# symbol the archives define whose name starts with "av", sorted and without duplicates, as a module-definition file.
# Data symbols are marked DATA. The archives keep their own members, so a symbol defined in both (file_open.c is
# compiled into each) is linked once, as in the earlier static link.
#
# cmake -DNM=<llvm-nm> -DAVUTIL=<libavutil.lib> -DAVCODEC=<libavcodec.lib> -DOUT=<ffmpeg.def> -P m46_ffmpeg_def.cmake
foreach(v NM AVUTIL AVCODEC OUT)
  if(NOT DEFINED ${v})
    message(FATAL_ERROR "m46_ffmpeg_def: ${v} not set")
  endif()
endforeach()
execute_process(
  COMMAND "${NM}" --defined-only --extern-only "${AVUTIL}" "${AVCODEC}"
  OUTPUT_VARIABLE listing
  RESULT_VARIABLE rc)
if(NOT rc EQUAL 0)
  message(FATAL_ERROR "m46_ffmpeg_def: ${NM} failed (${rc})")
endif()
string(REPLACE "\r" "" listing "${listing}")
string(REPLACE ";" "" listing "${listing}")
string(REPLACE "\n" ";" lines "${listing}")
set(code)
set(data)
foreach(line IN LISTS lines)
  if(line MATCHES "^[0-9a-fA-F]+ ([A-Za-z]) (av[A-Za-z0-9_]*)$")
    if(CMAKE_MATCH_1 STREQUAL "T")
      list(APPEND code "${CMAKE_MATCH_2}")
    else()
      list(APPEND data "${CMAKE_MATCH_2}")
    endif()
  endif()
endforeach()
list(REMOVE_DUPLICATES code)
list(REMOVE_DUPLICATES data)
list(REMOVE_ITEM data ${code})
list(SORT code)
list(SORT data)
list(LENGTH code n)
if(n LESS 100)
  message(FATAL_ERROR "m46_ffmpeg_def: only ${n} av* functions found; wrong archives?")
endif()
set(text "EXPORTS\n")
foreach(s IN LISTS code)
  string(APPEND text "    ${s}\n")
endforeach()
foreach(s IN LISTS data)
  string(APPEND text "    ${s} DATA\n")
endforeach()
# Rewrite only on change, so an unchanged list does not relink the DLL.
if(EXISTS "${OUT}")
  file(READ "${OUT}" old)
  if(old STREQUAL text)
    return()
  endif()
endif()
file(WRITE "${OUT}" "${text}")
