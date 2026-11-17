// LWR synthetic test leaves (SysV ABI). Not generated code: they are authorized
// only as explicitly synthetic code ranges by lwr_probe and by negative modes.
// Each store is a single instruction followed by ret; `_end` labels bound the
// range handed to lwr_authorize().
    .text
    .globl lwr_leaf_store8, lwr_leaf_store8_end
    .type lwr_leaf_store8,@function
lwr_leaf_store8:
    movb %sil, (%rdi)          // 40 88 37: REX + 88
    ret
lwr_leaf_store8_end:
    .size lwr_leaf_store8,.-lwr_leaf_store8

    .globl lwr_leaf_store32, lwr_leaf_store32_end
    .type lwr_leaf_store32,@function
lwr_leaf_store32:
    movl %esi, 4(%rdi)         // 89 77 04: disp8; caller passes address - 4
    ret
lwr_leaf_store32_end:
    .size lwr_leaf_store32,.-lwr_leaf_store32

    .globl lwr_leaf_store64, lwr_leaf_store64_end
    .type lwr_leaf_store64,@function
lwr_leaf_store64:
    movq %rsi, (%rdi,%rdx,1)   // 48 89 34 17: REX.W + SIB base/index
    ret
lwr_leaf_store64_end:
    .size lwr_leaf_store64,.-lwr_leaf_store64

    .globl lwr_leaf_store128, lwr_leaf_store128_end
    .type lwr_leaf_store128,@function
lwr_leaf_store128:
    movups %xmm0, (%rdi)       // 0f 11 07: SSE, never admitted
    ret
lwr_leaf_store128_end:
    .size lwr_leaf_store128,.-lwr_leaf_store128

    .globl lwr_leaf_load32, lwr_leaf_load32_end
    .type lwr_leaf_load32,@function
lwr_leaf_load32:
    movl (%rdi), %eax          // 8b 07: load, never admitted
    ret
lwr_leaf_load32_end:
    .size lwr_leaf_load32,.-lwr_leaf_load32
    .section .note.GNU-stack,"",@progbits
