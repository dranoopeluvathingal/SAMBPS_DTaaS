"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: Presentation Delivery
"""

import graphviz

def create_relay_flowchart():
    dot = graphviz.Digraph('Relay_Logic', comment='Adaptive IBR Protection Flow')
    dot.attr(rankdir='TB', size='8,10')
    dot.attr('node', shape='rectangle', style='filled', color='lightblue', fontname='Arial')

    # Nodes
    dot.node('START', 'START: Data Acquisition\n(Va, Vb, Vc, Ia, Ib, Ic)', shape='ellipse', color='lightgrey')
    dot.node('SEQ', 'Extract Symmetrical Components\n(V1, I1, I2)')
    dot.node('CHECK_V', 'Is V1 < V_threshold (0.9 p.u.)?', shape='diamond', color='orange')
    
    dot.node('LEGACY', 'Set Static Pickup\nI_set = I_nom (1.5 p.u.)')
    dot.node('ADAPTIVE', 'Calculate Adaptive Pickup\nI_set = f(V1, V_fault, I_min)')
    
    dot.node('COMPARE', 'Is I1 > I_set?', shape='diamond', color='orange')
    dot.node('TRIP', 'GENERATE TRIP SIGNAL\n(Breaker Open)', color='red', fontcolor='white')
    dot.node('MONITOR', 'Continue Monitoring', shape='ellipse', color='lightgrey')

    # Edges
    dot.edge('START', 'SEQ')
    dot.edge('SEQ', 'CHECK_V')
    
    dot.edge('CHECK_V', 'ADAPTIVE', label='YES (Fault/Disturbance)')
    dot.edge('CHECK_V', 'LEGACY', label='NO (Normal Operation)')
    
    dot.edge('ADAPTIVE', 'COMPARE')
    dot.edge('LEGACY', 'COMPARE')
    
    dot.edge('COMPARE', 'TRIP', label='YES')
    dot.edge('COMPARE', 'MONITOR', label='NO')

    # Save
    dot.render('relay_logic_flowchart', format='png', cleanup=True)
    print("SUCCESS: relay_logic_flowchart.png generated in ~/phd_thesis/")

if __name__ == "__main__":
    create_relay_flowchart()