// Fixed SysV leaf ABI: the faulting instruction changes no memory before the fault.
// Recovery labels return 1 without re-executing the access (no instruction retry).
    .text
    .globl lrb_load_leaf
    .type lrb_load_leaf,@function
lrb_load_leaf:
    .globl lrb_read_site
lrb_read_site:
    movl (%rdi), %eax
    movl %eax, (%rsi)
    xorl %eax, %eax
    ret
    .globl lrb_read_recover
lrb_read_recover:
    movl $1, %eax
    ret
    .size lrb_load_leaf,.-lrb_load_leaf

    .globl lrb_store_leaf
    .type lrb_store_leaf,@function
lrb_store_leaf:
    .globl lrb_write_site
lrb_write_site:
    movl %esi, (%rdi)
    xorl %eax, %eax
    ret
    .globl lrb_write_recover
lrb_write_recover:
    movl $1, %eax
    ret
    .size lrb_store_leaf,.-lrb_store_leaf

#ifdef LRB_TEST
// Negative-test leaf: a load from an instruction that is NOT an admitted site.
    .globl lrb_wrong_leaf
    .type lrb_wrong_leaf,@function
lrb_wrong_leaf:
    movl (%rdi), %eax
    ret
    .size lrb_wrong_leaf,.-lrb_wrong_leaf
#endif
    .section .note.GNU-stack,"",@progbits
