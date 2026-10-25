// M46 (D-084): drives the runtime's own LZX path (rexruntime.dll lzx_decompress -> mspack.dll lzxd_*) on one LZX
// stream, so that a replaced mspack.dll is exercised: this title's Default.xex uses basic compression and never
// reaches lzxd. tools/m46_lgpl.py feeds it the concatenated CFDATA payload of a Windows makecab LZX cabinet and
// compares the output with the original file.
//   m46_lzx_probe IN OUT SIZE WINDOW_SIZE   -> exit code = lzx_decompress result (0 = success)
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

int lzx_decompress(const void* lzx_data, size_t lzx_len, void* dest, size_t dest_len, uint32_t window_size,
                   void* window_data, size_t window_data_len);

static std::vector<unsigned char> read_all(const char* path) {
  std::vector<unsigned char> data;
  if (FILE* f = std::fopen(path, "rb")) {
    unsigned char buf[65536];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) data.insert(data.end(), buf, buf + n);
    std::fclose(f);
  }
  return data;
}

int main(int argc, char** argv) {
  if (argc != 5) {
    std::fprintf(stderr, "usage: m46_lzx_probe IN OUT SIZE WINDOW_SIZE\n");
    return 2;
  }
  std::vector<unsigned char> in = read_all(argv[1]);
  std::vector<unsigned char> out(std::strtoull(argv[3], nullptr, 10));
  uint32_t window = static_cast<uint32_t>(std::strtoul(argv[4], nullptr, 10));
  if (in.empty() || out.empty()) return 2;
  int rc = lzx_decompress(in.data(), in.size(), out.data(), out.size(), window, nullptr, 0);
  if (FILE* f = std::fopen(argv[2], "wb")) {
    std::fwrite(out.data(), 1, out.size(), f);
    std::fclose(f);
  }
  std::printf("M46_LZX_PROBE rc=%d in=%zu out=%zu window=%u\n", rc, in.size(), out.size(), window);
  return rc;
}
