	lea rcx, [rsi+rax]
	mov [rsp+16], rcx
	xor r8,  qword ptr [rcx+0]
	xor r9,  qword ptr [rcx+8]
	xor r10, qword ptr [rcx+16]
	xor r11, qword ptr [rcx+24]
	xor r12, qword ptr [rcx+32]
	xor r13, qword ptr [rcx+40]
	xor r14, qword ptr [rcx+48]
	xor r15, qword ptr [rcx+56]
	lea rcx, [rsi+rdx]
	mov [rsp+24], rcx

    vcvtdq2pd ymm0, xmmword ptr [rcx]
    vcvtdq2pd ymm2, xmmword ptr [rcx+16]
    vcvtdq2pd ymm4, xmmword ptr [rcx+32]
    vcvtdq2pd ymm6, xmmword ptr [rcx+48]
    vinsertf128 ymm12, ymm13, xmm13, 1
    vandpd ymm4, ymm4, ymm12
    vandpd ymm6, ymm6, ymm12
    vinsertf128 ymm12, ymm14, xmm14, 1
    vorpd ymm4, ymm4, ymm12
    vorpd ymm6, ymm6, ymm12
    vextractf128 xmm1, ymm0, 1
    vextractf128 xmm3, ymm2, 1
    vextractf128 xmm5, ymm4, 1
    vextractf128 xmm7, ymm6, 1
