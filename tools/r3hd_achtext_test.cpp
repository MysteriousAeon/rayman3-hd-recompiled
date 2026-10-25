// Test of tools/r3hd_achtext.h (D-101): SHA-256 against Python's hashlib, the file format, the English fallback for
// absent, empty, malformed and stale entries, and the description fallback for "unachieved". Synthetic text only.
// Ends with R3HD_ACHTEXT_TEST PASS n/n.
#include <cstdio>
#include <string>

#include "r3hd_achtext.h"

using namespace r3hd_achtext;

namespace {
int g_pass = 0, g_fail = 0;
void Check(const char* name, bool ok) {
  std::printf("%s %s\n", ok ? "ok  " : "FAIL", name);
  (ok ? g_pass : g_fail)++;
}
}  // namespace

int main() {
  // UTF-8 written as escapes so the source stays ASCII: "Başarı İçin ğış".
  const std::string tr = "Ba\xC5\x9F" "ar\xC4\xB1 \xC4\xB0\xC3\xA7in \xC4\x9F\xC4\xB1\xC5\x9F";
  Check("sha256 empty", Sha256Hex("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  Check("sha256 abc", Sha256Hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  Check("sha256 UTF-8", Sha256Hex(tr) == "7b63ab1f00d27007b654c3a1bf5fc028ccece3d84098b024b26529e0991028b4");
  Check("sha256 1000 bytes", Sha256Hex(std::string(1000, 'x')) ==
                                 "44f8354494a5ba03ba1792a8d3e9c534c47a9181980fde7a3f44b06ef2ae7c7f");

  const std::string en_label = "First", en_desc = "Do a thing.", en_label9 = "Second";
  std::string body = "# comment\r\n";
  body += "1\tlabel\t" + Sha256Hex(en_label) + "\t" + tr + "\r\n";
  body += "1\tdescription\t" + Sha256Hex(en_desc) + "\tBir \xC5\x9F" "ey yap.\n";
  body += "9\tlabel\t" + Sha256Hex("Old English") + "\tEski\n";      // stale: made from other English
  body += "2\tscore\t" + Sha256Hex("x") + "\t100\n";                   // not a text field
  body += "3\tlabel\tnothex\tx\n";                                     // bad hash
  body += "4\tlabel\t" + Sha256Hex("y") + "\t\n";                      // empty text
  body += "5\tlabel\t" + Sha256Hex("z") + "\ta\x01" "b\n";              // control character
  body += "0\tlabel\t" + Sha256Hex("z") + "\tzero\n";                  // id 0
  body += "no tabs here\n";
  Table t;
  const size_t kept = t.Parse(body);
  Check("three valid entries kept, six bad lines skipped", kept == 3 && t.skipped() == 6);
  Check("translated label shown", t.Display(1, kLabel, en_label, en_desc) == tr);
  Check("translated description shown", t.Display(1, kDescription, en_desc, en_desc) == "Bir \xC5\x9F" "ey yap.");
  Check("unachieved = description in English: takes the description's translation",
        t.Display(1, kUnachieved, en_desc, en_desc) == "Bir \xC5\x9F" "ey yap.");
  Check("unachieved with other English: stays English", t.Display(1, kUnachieved, "Locked.", en_desc) == "Locked.");
  Check("stale entry: English", t.Display(9, kLabel, en_label9, "") == en_label9 && t.stale() == 1);
  Check("stale counted once", (t.Display(9, kLabel, en_label9, ""), t.stale() == 1));
  Check("absent achievement: English", t.Display(12, kLabel, "Twelve", "") == "Twelve");
  Check("other English for a translated entry: English", t.Display(1, kLabel, "First!", en_desc) == "First!");
  Check("and the matching English still translated", t.Display(1, kLabel, en_label, en_desc) == tr);
  {  // one process-wide table, whatever the call site (the overlay and the toast pass different lambdas)
    const char* path = "r3hd_achtext_test.tsv";
    if (FILE* f = std::fopen(path, "wb")) {
      std::fputs(("1\tlabel\t" + Sha256Hex(en_label) + "\tBir\n").c_str(), f);
      std::fclose(f);
    }
    _putenv_s("R3HD_ACH_TEXT", path);
    static int lines = 0;
    const Table& a = Get([](const char*) { ++lines; });
    const Table& b = Get([](const char*) { ++lines; });
    Check("Get: one table for every call site, loaded once", &a == &b && lines == 1 && a.size() == 1 &&
                                                                 a.Display(1, kLabel, en_label, en_desc) == "Bir");
    std::remove(path);
  }
  Table empty;
  Check("empty file: nothing", empty.Parse("") == 0 && empty.Display(1, kLabel, en_label, en_desc) == en_label);
  std::printf("R3HD_ACHTEXT_TEST %s %d/%d\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail);
  return g_fail ? 1 : 0;
}
