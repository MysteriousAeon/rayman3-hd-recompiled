// Linux x86-64 SysV checked access leaves. No stack/red-zone/nonvolatile use.
    .text
    .globl lgf_load32
    .type lgf_load32,@function
lgf_load32:
    .globl lgf_load_site
lgf_load_site:
    movl (%rdi), %eax
    movl %eax, (%rsi)
    xorl %eax, %eax
    ret
    .globl lgf_load_recover
lgf_load_recover:
    movl $1, %eax
    ret
    .size lgf_load32, .-lgf_load32

#ifdef LGF_TEST
    .globl lgf_wrong_load32
    .type lgf_wrong_load32,@function
lgf_wrong_load32:
    movl (%rdi), %eax
    movl %eax, (%rsi)
    xorl %eax, %eax
    ret
    .size lgf_wrong_load32, .-lgf_wrong_load32
#endif
    .section .note.GNU-stack,"",@progbits
