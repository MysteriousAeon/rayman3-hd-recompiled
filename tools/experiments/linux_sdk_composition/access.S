// Fixed SysV leaf ABI: the faulting instruction changes no memory before fault.
    .text
    .globl lsc_load_leaf
    .type lsc_load_leaf,@function
lsc_load_leaf:
    .globl lsc_read_site
lsc_read_site:
    movl (%rdi), %eax
    movl %eax, (%rsi)
    xorl %eax, %eax
    ret
    .globl lsc_read_recover
lsc_read_recover:
    movl $1, %eax
    ret
    .size lsc_load_leaf,.-lsc_load_leaf

    .globl lsc_store_leaf
    .type lsc_store_leaf,@function
lsc_store_leaf:
    .globl lsc_write_site
lsc_write_site:
    movl %esi, (%rdi)
    xorl %eax, %eax
    ret
    .globl lsc_write_recover
lsc_write_recover:
    movl $1, %eax
    ret
    .size lsc_store_leaf,.-lsc_store_leaf

#ifdef LSC_TEST
    .globl lsc_wrong_leaf
    .type lsc_wrong_leaf,@function
lsc_wrong_leaf:
    movl (%rdi), %eax
    ret
    .size lsc_wrong_leaf,.-lsc_wrong_leaf
#endif
    .section .note.GNU-stack,"",@progbits
