function [A, B, C, D] = faultloc_pi_state_space(alpha, Rx)
%FAULTLOC_PI_STATE_SPACE  Two-section pi-model with HIF shunt at split node.
%
%   [A, B, C, D] = faultloc_pi_state_space(alpha, Rx)
%
%   Inputs
%     alpha  Per-unit fault location along the 100 km feeder, in (0, 1).
%     Rx     HIF arc resistance at the fault node, in ohm.
%
%   Outputs
%     A 4x4 state-matrix; B 4x1 input matrix; C 1x4 output; D scalar.
%     State vector x = [V_C1, V_C2, I_L1, I_L2].'  with V_C1 the voltage
%     at the fault node (= mid-bus 1), V_C2 the remote-end voltage,
%     I_L1, I_L2 the section-1 and section-2 inductor currents.
%     Input u = V_source(t).  Output y = I_source(t) = I_L1.
%
%   The structural property A(1,1) = -1/(R_x * C_1) is continuously
%   differentiable in (alpha, R_x); this is what the WP2.2 closed-form
%   gradient builds on.  WP0.5 owns the full Appendix-A derivation.

    L_total = 100;       % feeder length [km]
    Rp =  0.0728;        % per-km resistance [ohm/km]
    Lp =  0.927e-3;      % per-km inductance [H/km]
    Cp = 11.6e-9;        % per-km capacitance [F/km]
    Rload = 1e6;         % open-end remote-bus shunt [ohm]

    L1 = alpha       * L_total;
    L2 = (1 - alpha) * L_total;

    R1 = Rp * L1;   X1 = Lp * L1;   C1 = Cp * L1;
    R2 = Rp * L2;   X2 = Lp * L2;   C2 = Cp * L2;

    A = [ -1/(Rx*C1)   0         1/C1        -1/C1; ...
            0          -1/(Rload*C2) 0         1/C2; ...
           -1/X1       0         -R1/X1      0; ...
            1/X2      -1/X2      0          -R2/X2 ];

    B = [0; 0; 1/X1; 0];
    C = [0  0  1  0];
    D = 0;
end
