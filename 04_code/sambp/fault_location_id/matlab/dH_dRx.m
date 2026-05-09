function out = dH_dRx(alpha, Rx, omega)
%DH_DRX  Closed-form dH/dRx of the cascaded-Gamma transfer function.
%
%   Placeholder.  Auto-generated form is written by `derive_partials.m`
%   on a licensed MATLAB run; until then this fallback computes the
%   partial via central finite-difference (h = 1e-6) so downstream
%   code (the optimiser and the FIM) keeps running.
%
%   See docs/AppendixA_derivation.tex §A.5 for the symbolic form.

    h = 1e-6 * Rx;     % relative step for the resistance variable
    out = (H_at(alpha, Rx + h, omega) - H_at(alpha, Rx - h, omega)) / (2*h);
end


function H = H_at(alpha, Rx, omega)
    [A, B, C, D] = faultloc_pi_state_space(alpha, Rx);
    H = C * ((1j*omega*eye(size(A)) - A) \ B) + D;
end
