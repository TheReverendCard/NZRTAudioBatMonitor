idf_component_register(SRCS "WildlifeDetector.cpp" "probe.cpp" INCLUDE_DIRS "." REQUIRES freertos esp_timer)
target_compile_definitions(${COMPONENT_LIB} PRIVATE NZRT_HOST_TEST)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=misleading-indentation)
