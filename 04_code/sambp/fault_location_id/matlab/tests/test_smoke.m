classdef test_smoke < matlab.unittest.TestCase
    %TEST_SMOKE  WP0.4 sub-task 4 seed: sym/eig regression smoke test.
    %
    %   The v3 Execution Plan (docs/FaultLocationIdentification_ExecutionPlan.pdf)
    %   §4.1 WP0.4 sub-task 4 requires a CI-runnable symbolic regression
    %   test for the 4x4 state-space A-matrix derived in Appendix A
    %   (WP0.5).  This file is the seed: a minimal sym/eig sanity check
    %   that proves the Symbolic Math Toolbox is functional on the dev /
    %   CI machine before WP0.5 lands the project-specific A(alpha, Rx)
    %   matrix.
    %
    %   Future extensions (WP0.5 sign-off):
    %     * Replace the generic A = sym('a',[4 4]) with the
    %       project-specific A(alpha, Rx) from
    %       matlab/+faultloc/build_pi_state_space.m.
    %     * Verify A(1,1) == -1/(R_x * C_1) symbolically.
    %     * Verify dH/dalpha and dH/dRx match the Appendix-A
    %       hand-derivation up to algebraic equivalence (use simplify).

    methods (Test)

        function symEigReturnsFourSymbolicEigenvalues(testCase)
            % Smoke: 4x4 symbolic matrix has a 4-vector of symbolic
            % eigenvalues.  Establishes Symbolic Math Toolbox
            % availability for downstream WP0.5 / WP2.2 work.

            A = sym('a', [4 4]);
            ev = eig(A);

            testCase.verifyClass(ev, 'sym', ...
                'eig of a symbolic matrix should itself be symbolic');
            testCase.verifyLength(ev, 4, ...
                'a 4x4 matrix should yield exactly 4 eigenvalues');
        end

    end
end
