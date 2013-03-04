from __future__ import absolute_import

import re

from . import Processor
import makerbot_driver


class DualRetractProcessor(Processor):
    def __init__(self):
        super(DualRetractProcessor, self).__init__()
        self.layer_start = re.compile("^\((Slice|<layer>) [0-9.]+.*\)")
        self.snort = re.compile(
            "^G1 F[0-9.-]+ [AB]([0-9.-]+) \(snort\)|^G1 F[0-9.-]+\nG1 E([0-9.-]+)")
        self.squirt = re.compile(
            "^G1 F[0-9.-]+ [AB]([0-9.-]+) \(squirt\)|^G1 F[0-9.-]+\nG1 E([0-9.-]+)")
        self.toolchange = re.compile("^M135 T([0-9])")
        self.SF_feedrate = re.compile("^G1 F[0-9.-]+\n")
        self.purge = re.compile(".*purge.*|.*Purge.*")

        self.TOOLHEADS = ['A', 'B']

    def sandwich_iter(self, iterable):
        """
        This function returns an iterator with the previous,current,and next values
        in a iterable

        @param iterable: iterable object
        @return iterator of triplets
        """
        iterator = iter(iterable)
        current = iterator.next()
        prev = None

        for next in iterator:
            yield(prev,current,next)
            prev = current        
            current = next
        yield(prev,current,'')


    def process_gcode(self, gcode_in, profile_name):
        """
        This function adds retractions and squirt tweaks to a gcode input

        @param gcode_in: iterable object containing gcode
        @param profile_name: the name of the machine profile to use
        @return output: iterable containing the processed gcode
        """
        profile = makerbot_driver.profile.Profile(profile_name)

        self.retract_distance_mm = profile.values["dualstrusion"][
            "retract_distance_mm"]
        self.squirt_reduction_mm = profile.values["dualstrusion"][
            "squirt_reduce_mm"]
        self.squirt_feedrate = profile.values["dualstrusion"][
            "squirt_feedrate"]
        self.snort_feedrate = profile.values["dualstrusion"][
            "snort_feedrate"]

        self.current_tool = -1
        self.last_tool = -1
        self.last_snort = {'index': None, 'extruder_position':None}
        self.squirt_extruder_pos = None
        self.seeking_first_toolchange = True
        self.seeking_first_layer = True
        self.seeking_squirt = False
        self.SF_flag = False
        self.SF_handle_second_snortsquirt_line = False
        self.output = []

        for (previous_code,current_code,next_code) in self.sandwich_iter(gcode_in):    
            if(self.SF_handle_second_snortsquirt_line):
                self.SF_handle_second_snort_squirt_line = False
                continue

            self.output.append(current_code)

            if(self.seeking_squirt):
                if(self.check_for_squirt(current_code+next_code)):
                    self.squirt_replace()
            elif(self.seeking_first_layer):
                if(self.check_for_layer(current_code)):
                    self.seeking_first_layer = False
            else:
                if(self.check_for_snort(current_code+next_code)):
                    continue
                elif(self.check_for_significant_toolchange(current_code)):
                    if(self.seeking_first_toolchange):
                        match_prev = re.match(self.purge, previous_code)
                        match_next = re.match(self.purge, next_code)
                        if((match_prev is not None) or (match_next is not None)):
                            #If toolchanges are in the purge ignore
                            self.current_tool = self.last_tool
                            self.last_tool = -1
                            continue
                        #if this is the first significant toolchange do an extra squirt
                        self.seeking_first_toolchange = False
                        self.squirt_tool(self.current_tool)
                    self.snort_replace()
                    self.seeking_squirt = True

        #TODO: not worry about this and let the purge handle it?
        #Squirt retracted tool at the end of the print
        self.squirt_tool(self.get_other_tool(self.current_tool))

        return self.output


    def check_for_layer(self,string):
        match = re.match(self.layer_start, string)
        return match is not None


    def check_for_snort(self,string):
        """
        Check to see if string is a snort
        if so it save the snort values and returns
        
        @param string: string to be matched with the regex
        @return boolean: True if it is a snort
        """
        match = re.match(self.snort, string)
        if match is not None:
            extruder_position = match.group(1)
            if(extruder_position == None):
                extruder_position = match.group(2)
            self.last_snort['index'] = len(self.output)-1
            self.last_snort['extruder_position'] = float(extruder_position)
            #Check if this is a SF snort
            match = re.match(self.SF_feedrate, string)
            if match is not None:
                self.SF_flag = True
            return True
        else:
            return False


    def check_for_significant_toolchange(self,string):
        """
        Checks for significant toolchange(i.e. from tool 0 -> 1)
        Updates the current tool accordingly

        @param string: string to be matched to toolchange regex
        @return boolean: True if a significant toolchange is found
        """
        match = re.match(self.toolchange, string)
        if match is not None:
            if(self.current_tool == -1):
                self.current_tool = int(match.group(1))
                return False
            elif(self.current_tool != int(match.group(1))):
                self.last_tool = self.current_tool
                self.current_tool = int(match.group(1))
                return True
            else:
                return False
        else:
            return False


    def check_for_squirt(self, string):
        """
        Check if string contains a squirt

        @param string: string to be matched to squirt regex
        @return boolean: True if squirt was found
        """
        match = re.match(self.squirt, string)
        if match is not None:
            extruder_position = match.group(1)
            if(extruder_position == None):
                extruder_position = match.group(2)
            self.squirt_extruder_pos = float(extruder_position)
            match = re.match(self.SF_feedrate, string)
            if match is not None:
                self.SF_handle_second_squirt_line = True
            self.seeking_squirt = False
            return True
        else:
            return False


    def get_other_tool(self, tool):
        inactive_tool = {0:1, 1:0}
        try:
            return inactive_tool[tool]
        except:
            return -1


    def squirt_tool(self, tool):
        self.output.append("M135 T%i\n"%(tool))
        self.output.append("G92 %s0\n"%(self.TOOLHEADS[tool]))
        self.output.append("G1 F%f %s%f\n"%(self.squirt_feedrate, self.TOOLHEADS[tool],
            self.retract_distance_mm))
        self.output.append("G92 %s0\n"%(self.TOOLHEADS[tool]))
        self.output.append("M135 T%i\n"%(tool))
        

    def squirt_replace(self):
        new_extruder_position = self.squirt_extruder_pos-self.squirt_reduction_mm

        squirt_line = "G1 F%f %s%f\n"%(self.squirt_feedrate, self.TOOLHEADS[self.current_tool],
            new_extruder_position)
        self.output[-1] = squirt_line


    def snort_replace(self):
        """
        Replaces a past snort
        """
        if(self.last_snort['index'] != None):
            snort_index = self.last_snort['index']
            snort_extruder_position = self.last_snort['extruder_position']
            new_extruder_position = snort_extruder_position-self.retract_distance_mm

            snort_line = "G1 F%f %s%f\n"%(self.snort_feedrate, self.TOOLHEADS[self.last_tool],
                new_extruder_position)
            self.output[snort_index] = snort_line
            #if SF replace second line of the snort with a blank line
            if(self.SF_flag):
                self.output[snort_index+1] = '\n'

            #Reset Last Snort
            self.last_snort['index'] = None
            self.last_snort['extruder_position'] = None

