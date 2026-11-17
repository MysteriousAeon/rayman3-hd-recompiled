// Independent SysV x86-64 Linux signal-return probe, not a runtime helper.
// context_snapshot offsets are asserted by context_fixture.c.  No C call is
// made between seeding and recording the interrupted registers.
    .text
    .globl lgf_context_probe
    .type lgf_context_probe,@function
lgf_context_probe:                    // rdi=faulting page, rsi=snapshot
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $16, %rsp
    fnstcw 0(%rsp)                  // restore caller's FP control later
    stmxcsr 4(%rsp)
    movzwl 0(%rsp), %eax
    andl $0xf3ff, %eax
    orl $0x0400, %eax              // x87 round downward
    movw %ax, 8(%rsp)
    fldcw 8(%rsp)
    movw %ax, 96(%rsi)
    movl 4(%rsp), %eax
    andl $0xffff9fff, %eax
    orl $0x2000, %eax              // MXCSR round downward
    movl %eax, 12(%rsp)
    ldmxcsr 12(%rsp)
    movl %eax, 88(%rsi)
    movq %rsp, 0(%rsi)
    movabsq $0x1122334455667788, %rbx
    movabsq $0x2233445566778899, %rbp
    movabsq $0x33445566778899aa, %r12
    movabsq $0x445566778899aabb, %r13
    movabsq $0x5566778899aabbcc, %r14
    movabsq $0x66778899aabbccdd, %r15
    movdqu .Lxmm0(%rip), %xmm0
    movdqu .Lxmm15(%rip), %xmm15
    stc
    pushfq
    popq 72(%rsi)
    movabsq $0x78abcdef12345609, %rax
    movq %rax, -8(%rsp)            // SysV red zone, never use after pushfq
    .globl lgf_context_fault_site
lgf_context_fault_site:
    movl (%rdi), %eax              // SIGSEGV expected; no output side effect
    .globl lgf_context_recovery
lgf_context_recovery:
    movq %rsp, 8(%rsi)
    movq %rbx, 16(%rsi)
    movq %rbp, 24(%rsi)
    movq %r12, 32(%rsi)
    movq %r13, 40(%rsi)
    movq %r14, 48(%rsi)
    movq %r15, 56(%rsi)
    movq -8(%rsp), %rax
    movq %rax, 64(%rsi)
    pushfq
    popq 80(%rsi)
    stmxcsr 92(%rsi)
    fnstcw 98(%rsi)
    movdqu %xmm0, 112(%rsi)
    movdqu %xmm15, 128(%rsi)
    fldcw 0(%rsp)
    ldmxcsr 4(%rsp)
    addq $16, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
    .size lgf_context_probe, .-lgf_context_probe
    .section .rodata
    .balign 16
.Lxmm0:
    .quad 0x0123456789abcdef, 0xfedcba9876543210
.Lxmm15:
    .quad 0x13579bdf2468ace0, 0x02468ace13579bdf
    .section .note.GNU-stack,"",@progbits
