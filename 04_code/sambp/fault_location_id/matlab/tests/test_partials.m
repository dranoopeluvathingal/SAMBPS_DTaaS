classdef test_partials < matlab.unittest.TestCase
    %TEST_PARTIALS  WP0.5 - analytic dH/dtheta vs finite-difference.
    %
    %   Compares the analytic gradients in matlab/dH_dalpha.m and
    %   matlab/dH_dRx.m against a 1e-6 central finite-difference at
    %   three (alpha, R_x) pairs spanning the operating envelope.
    %   Pass criterion: max |analytic - FD| / max(1, |analytic|) <
    %   tol_rel.
    %
    %   When derive_partials.m has been run on a licensed MATLAB,
    %   dH_dalpha and dH_dRx are the auto-generated symbolic forms
    %   and the comparison is to symbolic-precision (~1e-12).  Until
    %   then the placeholder implementations are FD themselves and
    %   the test trivially passes (sanity).

    properties (Constant)
        cases = {[0.30, 500];  [0.50, 1000];  [0.70, 2000]};
        omega = 2*pi*50;
        h_alpha = 1e-6;
        h_Rx_rel = 1e-6;
        tol_rel = 1e-3;
    end

    methods (Test)

        function dHdalphaMatchesFD(testCase)
            for k = 1:numel(testCase.cases)
                p = testCase.cases{k};
                a = p(1); R = p(2);
                fd = (H_at(a + testCase.h_alpha, R, testCase.omega) ...
                    - H_at(a - testCase.h_alpha, R, testCase.omega)) ...
                    / (2*testCase.h_alpha);
                an = dH_dalpha(a, R, testCase.omega);
                rel = abs(an - fd) / max(1, abs(an));
                testCase.verifyLessThan(rel, testCase.tol_rel, ...
                    sprintf(['dH/dalpha@(a=%.2f,R=%.0f): rel err %.3e ', ...
                             '>= tol %.0e (an=%s, fd=%s)'], ...
                             a, R, rel, testCase.tol_rel, ...
                             num2str(an), num2str(fd)));
            end
        end

        function dHdRxMatchesFD(testCase)
            for k = 1:numel(testCase.cases)
                p = testCase.cases{k};
                a = p(1); R = p(2);
                h = testCase.h_Rx_rel * R;
                fd = (H_at(a, R + h, testCase.omega) ...
                    - H_at(a, R - h, testCase.omega)) ...
                    / (2*h);
                an = dH_dRx(a, R, testCase.omega);
                rel = abs(an - fd) / max(1, abs(an));
                testCase.verifyLessThan(rel, testCase.tol_rel, ...
                    sprintf(['dH/dRx@(a=%.2f,R=%.0f): rel err %.3e ', ...
                             '>= tol %.0e (an=%s, fd=%s)'], ...
                             a, R, rel, testCase.tol_rel, ...
                             num2str(an), num2str(fd)));
            end
        end

    end
end


function H = H_at(alpha, Rx, omega)
    [A, B, C, D] = faultloc_pi_state_space(alpha, Rx);
    H = C * ((1j*omega*eye(size(A)) - A) \ B) + D;
end
